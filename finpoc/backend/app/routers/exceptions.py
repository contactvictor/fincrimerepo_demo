import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import check_domain
from ..models import ReconException, User
from ..schemas import ExceptionDetailOut, ExceptionOut, TransitionRequest
from ..security import require
from ..services import ai
from ..services.workflow import allowed_transitions, transition

router = APIRouter(prefix="/api/exceptions", tags=["exceptions"])

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _filtered(run_id, domain, category, severity, status, root_cause, owner, search):
    stmt = select(ReconException)
    for col, value in ((ReconException.run_id, run_id), (ReconException.owner, owner)):
        if value is not None:
            stmt = stmt.where(col == value)
    for col, value in ((ReconException.domain, domain), (ReconException.category, category),
                       (ReconException.severity, severity), (ReconException.status, status),
                       (ReconException.root_cause, root_cause)):
        if value:
            stmt = stmt.where(col.in_(value.split(",")))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(ReconException.code.ilike(like), ReconException.record_key.ilike(like),
                              ReconException.description.ilike(like)))
    return stmt


def _detail(exc: ReconException) -> ExceptionDetailOut:
    out = ExceptionDetailOut.model_validate(exc)
    out.allowed_transitions = allowed_transitions(exc.status)
    return out


@router.get("")
def list_exceptions(run_id: int | None = None, domain: str | None = None, category: str | None = None,
                    severity: str | None = None, status: str | None = None, root_cause: str | None = None,
                    owner: str | None = None, search: str | None = None,
                    sort: str = Query("severity", pattern="^(severity|created_at|code|variance)$"),
                    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                    db: Session = Depends(get_db), _: User = Depends(require("exceptions:read"))):
    stmt = _filtered(run_id, domain, category, severity, status, root_cause, owner, search)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    from sqlalchemy import case

    order = {
        "severity": [case(SEVERITY_ORDER, value=ReconException.severity), ReconException.created_at.desc()],
        "created_at": [ReconException.created_at.desc()],
        "code": [ReconException.code],
        "variance": [func.abs(ReconException.variance).desc()],
    }[sort]
    items = db.scalars(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size))
    return {"total": total, "page": page, "page_size": page_size,
            "items": [ExceptionOut.model_validate(e) for e in items]}


@router.get("/export")
def export_exceptions(run_id: int | None = None, domain: str | None = None, category: str | None = None,
                      severity: str | None = None, status: str | None = None, root_cause: str | None = None,
                      owner: str | None = None, search: str | None = None, db: Session = Depends(get_db),
                      _: User = Depends(require("exceptions:read"))):
    stmt = _filtered(run_id, domain, category, severity, status, root_cause, owner, search)
    buf = io.StringIO()
    writer = csv.writer(buf)
    cols = ["code", "run_id", "domain", "category", "severity", "root_cause", "record_key", "field",
            "source_value", "target_value", "variance", "owner", "status", "created_at", "description"]
    writer.writerow(cols)
    for e in db.scalars(stmt.order_by(ReconException.code)):
        writer.writerow([getattr(e, c) for c in cols])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="exceptions.csv"'})


def _get(db: Session, code: str) -> ReconException:
    exc = db.scalar(select(ReconException).options(selectinload(ReconException.history))
                    .where(ReconException.code == code))
    if not exc:
        raise HTTPException(404, f"Exception {code} not found")
    return exc


@router.get("/{code}", response_model=ExceptionDetailOut)
def get_exception(code: str, db: Session = Depends(get_db), _: User = Depends(require("exceptions:read"))):
    return _detail(_get(db, code))


@router.post("/{code}/transition", response_model=ExceptionDetailOut)
def move(code: str, body: TransitionRequest, db: Session = Depends(get_db),
         user: User = Depends(require("exceptions:update"))):
    exc = _get(db, code)
    check_domain(user, exc.domain)
    if body.owner and not db.scalar(select(User).where(User.username == body.owner, User.active.is_(True))):
        raise HTTPException(400, f"Unknown owner '{body.owner}'")
    transition(db, exc, body.to_status, user, body.owner, body.comment)
    db.commit()
    db.expire(exc)
    return _detail(_get(db, code))


@router.get("/{code}/explain")
def explain(code: str, db: Session = Depends(get_db), _: User = Depends(require("exceptions:read"))):
    return ai.explain_exception(db, _get(db, code))
