"""Exception lifecycle: Detected -> Assigned -> Investigating -> Resolved -> Closed."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..constants import ExceptionStatus as S
from ..models import ExceptionHistory, ReconException, User, utcnow
from .audit import log_action

TRANSITIONS: dict[str, set[str]] = {
    S.DETECTED.value: {S.ASSIGNED.value},
    S.ASSIGNED.value: {S.INVESTIGATING.value, S.ASSIGNED.value},
    S.INVESTIGATING.value: {S.RESOLVED.value, S.ASSIGNED.value},
    S.RESOLVED.value: {S.CLOSED.value, S.INVESTIGATING.value},
    S.CLOSED.value: set(),
}
OPEN_STATUSES = {S.DETECTED.value, S.ASSIGNED.value, S.INVESTIGATING.value}


def allowed_transitions(status: str) -> list[str]:
    return sorted(TRANSITIONS.get(status, set()))


def transition(db: Session, exc: ReconException, to_status: str, actor: User,
               owner: str | None = None, comment: str = "") -> ReconException:
    if to_status not in TRANSITIONS.get(exc.status, set()):
        raise HTTPException(400, f"Cannot move exception from {exc.status} to {to_status}. "
                                 f"Allowed: {allowed_transitions(exc.status) or 'none'}")
    if to_status == S.ASSIGNED.value:
        if not owner:
            raise HTTPException(400, "An owner is required to assign an exception")
        exc.owner = owner
    if to_status == S.RESOLVED.value:
        if not comment.strip():
            raise HTTPException(400, "A resolution comment is required to resolve an exception")
        exc.resolution = comment
    if to_status == S.CLOSED.value and actor.username == (exc.owner or "") and actor.role != "admin":
        raise HTTPException(400, "Four-eyes control: the owner cannot close their own exception")
    db.add(ExceptionHistory(exception_id=exc.id, from_status=exc.status, to_status=to_status,
                            actor=actor.username, comment=comment))
    log_action(db, actor.username, "EXCEPTION_TRANSITION", "exception", exc.code,
               {"from": exc.status, "to": to_status, "owner": exc.owner, "comment": comment})
    exc.status = to_status
    exc.updated_at = utcnow()
    return exc
