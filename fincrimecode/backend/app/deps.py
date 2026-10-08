from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import MigrationRun, User
from .security import can_access_domain


def get_run_or_404(db: Session, run_id: int) -> MigrationRun:
    run = db.get(MigrationRun, run_id)
    if not run:
        raise HTTPException(404, f"Migration run {run_id} not found")
    return run


def check_domain(user: User, domain: str) -> None:
    if not can_access_domain(user.role, domain):
        raise HTTPException(403, f"Role '{user.role}' is not permitted to act on the {domain} domain")
