from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db
from ..models import AuditLog, User
from ..schemas import AuditLogOut, UserCreate, UserOut, UserUpdate
from ..security import get_current_user, has_permission, hash_password, require
from ..services.audit import log_action

router = APIRouter(prefix="/api/admin", tags=["administration"])


@router.get("/users", response_model=list[UserOut])
def users(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require("admin"))):
    if body.role not in {r.value for r in Role}:
        raise HTTPException(400, f"role must be one of {[r.value for r in Role]}")
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "Username already exists")
    user = User(username=body.username, full_name=body.full_name, email=body.email, role=body.role,
                password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    log_action(db, actor.username, "USER_CREATED", "user", user.id, {"username": user.username, "role": user.role})
    db.commit()
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db),
                actor: User = Depends(require("admin"))):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if body.role and body.role not in {r.value for r in Role}:
        raise HTTPException(400, "Invalid role")
    changes = body.model_dump(exclude_none=True, exclude={"password"})
    for k, v in changes.items():
        setattr(user, k, v)
    if body.password:
        user.password_hash = hash_password(body.password)
        changes["password"] = "***"
    log_action(db, actor.username, "USER_UPDATED", "user", user.id, changes)
    db.commit()
    return user


@router.get("/audit-logs", response_model=list[AuditLogOut])
def audit_logs(action: str | None = None, actor: str | None = None, limit: int = Query(200, le=1000),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not (has_permission(user.role, "audit:read") or has_permission(user.role, "admin")):
        raise HTTPException(403, "Missing permission: audit:read")
    stmt = select(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    return list(db.scalars(stmt.limit(limit)))
