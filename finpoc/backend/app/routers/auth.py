from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import MeOut, TokenOut
from ..security import PERMISSIONS, ROLE_DOMAINS, create_access_token, get_current_user, verify_password
from ..services.audit import log_action

router = APIRouter(prefix="/api/auth", tags=["auth"])


def me_out(user: User) -> MeOut:
    return MeOut(id=user.id, username=user.username, full_name=user.full_name, email=user.email,
                 role=user.role, active=user.active, permissions=sorted(PERMISSIONS.get(user.role, set())),
                 domains=sorted(d) if (d := ROLE_DOMAINS.get(user.role)) is not None else None)


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not user.active or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    log_action(db, user.username, "LOGIN", "user", user.id)
    db.commit()
    return TokenOut(access_token=create_access_token(user), user=me_out(user))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return me_out(user)
