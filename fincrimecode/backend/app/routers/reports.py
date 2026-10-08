from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from ..db import get_db
from ..deps import get_run_or_404
from ..models import Report, User
from ..schemas import ReportOut, ReportRequest
from ..security import REPORT_PERMISSIONS, has_permission, require
from ..services import reporting
from ..services.audit import log_action

router = APIRouter(prefix="/api/reports", tags=["reports"])


def allowed_types(user: User) -> list[str]:
    if has_permission(user.role, "*"):
        return list(reporting.REPORT_TYPES)
    return [t for t in reporting.REPORT_TYPES if t in REPORT_PERMISSIONS.get(user.role, set())]


@router.get("/types")
def types(user: User = Depends(require("reports:read"))):
    allowed = set(allowed_types(user))
    return [{"type": k, "format": fmt, "title": title, "allowed": k in allowed}
            for k, (fmt, title) in reporting.REPORT_TYPES.items()]


@router.get("", response_model=list[ReportOut])
def list_reports(run_id: int | None = None, db: Session = Depends(get_db),
                 _: User = Depends(require("reports:read"))):
    stmt = select(Report).options(defer(Report.content)).order_by(Report.created_at.desc())
    if run_id:
        stmt = stmt.where(Report.run_id == run_id)
    return list(db.scalars(stmt.limit(200)))


@router.post("", response_model=ReportOut, status_code=201)
def generate(body: ReportRequest, db: Session = Depends(get_db), user: User = Depends(require("reports:read"))):
    if body.report_type not in reporting.REPORT_TYPES:
        raise HTTPException(400, f"report_type must be one of {list(reporting.REPORT_TYPES)}")
    if body.report_type not in allowed_types(user):
        raise HTTPException(403, f"Role '{user.role}' cannot generate {body.report_type}")
    run = get_run_or_404(db, body.run_id)
    if run.status != "COMPLETED":
        raise HTTPException(400, "Run must be reconciled before generating reports")
    report = reporting.generate(db, run, body.report_type, user.username)
    log_action(db, user.username, "REPORT_GENERATED", "report", report.id,
               {"run_id": run.id, "type": body.report_type, "sha256": report.sha256})
    db.commit()
    return report


@router.get("/{report_id}/download")
def download(report_id: int, db: Session = Depends(get_db), user: User = Depends(require("reports:read"))):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    log_action(db, user.username, "REPORT_DOWNLOADED", "report", report.id, {"run_id": report.run_id})
    db.commit()
    return Response(report.content, media_type=report.content_type, headers={
        "Content-Disposition": f'attachment; filename="{report.filename}"', "X-Content-SHA256": report.sha256})
