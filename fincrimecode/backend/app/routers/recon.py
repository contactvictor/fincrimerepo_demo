import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..constants import DOMAIN_SPECS
from ..db import get_db
from ..deps import get_run_or_404
from ..models import ReconSummary, RecordResult, User
from ..schemas import RecordOut, SummaryOut
from ..security import require

router = APIRouter(prefix="/api/recon", tags=["reconciliation"])


def _record_query(run_id: int, domain: str, status: str | None, search: str | None):
    if domain not in DOMAIN_SPECS:
        raise HTTPException(400, f"Unknown domain {domain}")
    stmt = select(RecordResult).where(RecordResult.run_id == run_id, RecordResult.domain == domain)
    if status:
        stmt = stmt.where(RecordResult.status.in_(status.split(",")))
    if search:
        stmt = stmt.where(or_(RecordResult.record_key.ilike(f"%{search}%")))
    return stmt


@router.get("/{run_id}/summary", response_model=list[SummaryOut])
def summary(run_id: int, domain: str | None = None, db: Session = Depends(get_db),
            _: User = Depends(require("recon:read"))):
    get_run_or_404(db, run_id)
    stmt = select(ReconSummary).where(ReconSummary.run_id == run_id)
    if domain:
        stmt = stmt.where(ReconSummary.domain == domain)
    return list(db.scalars(stmt.order_by(ReconSummary.domain, ReconSummary.id)))


@router.get("/{run_id}/records")
def records(run_id: int, domain: str, status: str | None = None, search: str | None = None,
            page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
            db: Session = Depends(get_db), _: User = Depends(require("recon:read"))):
    get_run_or_404(db, run_id)
    stmt = _record_query(run_id, domain, status, search)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = [RecordResult.status != "MISSING_IN_TARGET", RecordResult.status == "MATCHED",
             RecordResult.variance.desc(), RecordResult.record_key]
    items = db.scalars(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size))
    counts = dict(db.execute(select(RecordResult.status, func.count())
                             .where(RecordResult.run_id == run_id, RecordResult.domain == domain)
                             .group_by(RecordResult.status)).all())
    return {"total": total, "page": page, "page_size": page_size, "status_counts": counts,
            "fields": DOMAIN_SPECS[domain]["fields"], "key": DOMAIN_SPECS[domain]["key"],
            "items": [RecordOut.model_validate(r) for r in items]}


@router.get("/{run_id}/records/export")
def export_records(run_id: int, domain: str, status: str | None = None, search: str | None = None,
                   db: Session = Depends(get_db), _: User = Depends(require("recon:read"))):
    get_run_or_404(db, run_id)
    fields = DOMAIN_SPECS[domain]["fields"] if domain in DOMAIN_SPECS else []
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["record_key", "status", "variance", "fields_different",
                     *[f"source_{f}" for f in fields], *[f"target_{f}" for f in fields]])
    for r in db.scalars(_record_query(run_id, domain, status, search).order_by(RecordResult.record_key)):
        src, tgt = r.source_data or {}, r.target_data or {}
        writer.writerow([r.record_key, r.status, r.variance,
                         ";".join(d["field"] for d in r.field_differences or []),
                         *[src.get(f) for f in fields], *[tgt.get(f) for f in fields]])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="run{run_id}_{domain}_records.csv"'})


@router.get("/{run_id}/records/{domain}/{record_key}", response_model=RecordOut)
def record_detail(run_id: int, domain: str, record_key: str, db: Session = Depends(get_db),
                  _: User = Depends(require("recon:read"))):
    rec = db.scalar(select(RecordResult).where(RecordResult.run_id == run_id, RecordResult.domain == domain,
                                               RecordResult.record_key == record_key))
    if not rec:
        raise HTTPException(404, "Record not found")
    return rec


@router.get("/{run_id}/fields/{domain}")
def field_breakdown(run_id: int, domain: str, db: Session = Depends(get_db),
                    _: User = Depends(require("recon:read"))):
    """Level 3: mismatch counts per field."""
    if domain not in DOMAIN_SPECS:
        raise HTTPException(400, f"Unknown domain {domain}")
    counts = {f: 0 for f in DOMAIN_SPECS[domain]["fields"]}
    variance = {f: 0.0 for f in DOMAIN_SPECS[domain]["fields"]}
    compared = 0
    for status, diffs in db.execute(select(RecordResult.status, RecordResult.field_differences)
                                    .where(RecordResult.run_id == run_id, RecordResult.domain == domain)):
        if status in {"MATCHED", "MISMATCHED"}:
            compared += 1
        for d in diffs or []:
            counts[d["field"]] = counts.get(d["field"], 0) + 1
            variance[d["field"]] = variance.get(d["field"], 0.0) + abs(d.get("difference") or 0)
    return [{"field": f, "mismatches": c, "abs_variance": round(variance[f], 2), "compared": compared,
             "match_pct": round(100 * (compared - c) / compared, 2) if compared else None}
            for f, c in counts.items()]


