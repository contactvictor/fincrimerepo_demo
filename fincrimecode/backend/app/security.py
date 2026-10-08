import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .constants import Role
from .db import get_db
from .models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_PBKDF2_ITERATIONS = 200_000

PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN.value: {"*"},
    Role.ANALYST.value: {
        "dashboard:read", "runs:read", "recon:read", "exceptions:read", "exceptions:update",
        "reports:read", "reports:generate", "ai:use", "signoff:OPERATIONS",
    },
    Role.FINANCE.value: {
        "dashboard:read", "runs:read", "recon:read", "recon:execute", "exceptions:read",
        "exceptions:update", "reports:read", "reports:generate", "ai:use", "signoff:FINANCE",
    },
    Role.COMPLIANCE.value: {
        "dashboard:read", "runs:read", "recon:read", "recon:execute", "exceptions:read",
        "exceptions:update", "reports:read", "reports:generate", "ai:use",
        "signoff:AML", "signoff:COMPLIANCE",
    },
    Role.AUDITOR.value: {
        "dashboard:read", "runs:read", "recon:read", "exceptions:read", "reports:read",
        "reports:audit", "audit:read",
    },
}

# Report types each non-admin role may generate.
REPORT_PERMISSIONS: dict[str, set[str]] = {
    Role.ANALYST.value: {"BUSINESS_RECONCILIATION", "MIGRATION_SUMMARY", "MANAGEMENT_SUMMARY",
                         "DETAILED_MISMATCH"},
    Role.FINANCE.value: {"BUSINESS_RECONCILIATION", "MIGRATION_SUMMARY", "DETAILED_MISMATCH",
                         "MANAGEMENT_SUMMARY"},
    Role.COMPLIANCE.value: {"COMPLIANCE", "DETAILED_MISMATCH", "BUSINESS_RECONCILIATION"},
    Role.AUDITOR.value: {"AUDIT_PACK"},
}

# Domains a role may validate / act on. None means all domains.
ROLE_DOMAINS: dict[str, set[str] | None] = {
    Role.ADMIN.value: None,
    Role.ANALYST.value: None,
    Role.FINANCE.value: {"balance", "account", "transaction"},
    Role.COMPLIANCE.value: {"aml", "kyc", "sanctions", "customer"},
    Role.AUDITOR.value: None,
}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = encoded.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "role": user.role,
        "name": user.full_name,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def has_permission(role: str, permission: str) -> bool:
    perms = PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


def can_access_domain(role: str, domain: str) -> bool:
    allowed = ROLE_DOMAINS.get(role)
    return allowed is None or domain in allowed


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise credentials_error from exc
    user = db.scalar(select(User).where(User.username == payload.get("sub")))
    if user is None or not user.active:
        raise credentials_error
    return user


def require(permission: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return user

    return dependency
