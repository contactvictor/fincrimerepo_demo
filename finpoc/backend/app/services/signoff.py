from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..constants import DOMAIN_SIGNOFF_AREA, SignOffArea, SignOffDecision
from ..models import MigrationRun, ReconException, SignOff, User
from ..security import has_permission
from .audit import log_action
from .workflow import OPEN_STATUSES


def area_domains(area: str) -> list[str]:
    return [d for d, a in DOMAIN_SIGNOFF_AREA.items() if a == area]


def blocking_exceptions(db: Session, run_id: int, area: str) -> int:
    return db.scalar(select(func.count()).select_from(ReconException).where(
        ReconException.run_id == run_id, ReconException.domain.in_(area_domains(area)),
        ReconException.severity == "CRITICAL", ReconException.status.in_(OPEN_STATUSES))) or 0


def latest_signoffs(db: Session, run_id: int) -> dict[str, SignOff]:
    latest: dict[str, SignOff] = {}
    for s in db.scalars(select(SignOff).where(SignOff.run_id == run_id).order_by(SignOff.at, SignOff.id)):
        latest[s.area] = s
    return latest


def compute_status(db: Session, run: MigrationRun) -> str:
    latest = latest_signoffs(db, run.id)
    if any(s.decision == SignOffDecision.REJECTED.value for s in latest.values()):
        return "REJECTED"
    approved = {a for a, s in latest.items() if s.decision == SignOffDecision.APPROVED.value}
    if approved >= {a.value for a in SignOffArea}:
        return "APPROVED"
    return "PARTIAL" if approved else "PENDING"


def record_signoff(db: Session, run: MigrationRun, area: str, decision: str, comment: str,
                   user: User) -> SignOff:
    if area not in {a.value for a in SignOffArea}:
        raise HTTPException(400, f"Unknown sign-off area {area}")
    if decision not in {d.value for d in SignOffDecision}:
        raise HTTPException(400, "Decision must be APPROVED or REJECTED")
    if not has_permission(user.role, f"signoff:{area}"):
        raise HTTPException(403, f"Role '{user.role}' cannot sign off {area}")
    if run.status != "COMPLETED":
        raise HTTPException(400, "Reconciliation must be completed before sign-off")
    if decision == SignOffDecision.APPROVED.value:
        blockers = blocking_exceptions(db, run.id, area)
        if blockers:
            raise HTTPException(400, f"{blockers} open CRITICAL exception(s) in {area} domains block approval")
    signoff = SignOff(run_id=run.id, area=area, decision=decision, comment=comment,
                      actor=user.username, role=user.role)
    db.add(signoff)
    db.flush()
    run.signoff_status = compute_status(db, run)
    log_action(db, user.username, f"SIGNOFF_{decision}", "migration_run", run.id,
               {"area": area, "comment": comment})
    return signoff
