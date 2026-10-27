"""Role-based login: scrypt password hashes and server-side sessions in an HttpOnly cookie."""
import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models.platform import AuditEvent, User, UserSession

ROLES = {
    "reviewer": "Reviewer",
    "qc_analyst": "QC Analyst",
    "qc_lead": "QC Lead",
    "field_verifier": "Field Verifier",
    "ops_manager": "Operations Manager",
}
SESSION_COOKIE = "jsan_session"
SESSION_TTL = timedelta(hours=12)
MIN_PASSWORD_LENGTH = 10
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}

_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()
MAX_FAILURES, FAILURE_WINDOW = 5, 300


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), dklen=32, **_SCRYPT)
        return hmac.compare_digest(candidate, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(422, f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.")


def validate_roles(roles: list[str]) -> list[str]:
    unknown = sorted(set(roles) - set(ROLES))
    if unknown or not roles:
        raise HTTPException(422, f"Choose at least one role from: {', '.join(ROLES)}." + (f" Unknown: {', '.join(unknown)}." if unknown else ""))
    return sorted(set(roles))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_login_rate(key: str) -> None:
    with _failures_lock:
        recent = [t for t in _failures.get(key, []) if time.monotonic() - t < FAILURE_WINDOW]
        _failures[key] = recent
        if len(recent) >= MAX_FAILURES:
            raise HTTPException(429, "Too many failed sign-in attempts. Wait a few minutes and try again.")


def record_login_failure(key: str) -> None:
    with _failures_lock:
        _failures.setdefault(key, []).append(time.monotonic())


def clear_login_failures(key: str) -> None:
    with _failures_lock:
        _failures.pop(key, None)


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(UserSession(user_id=user.id, token_hash=_token_hash(token), expires_at=now() + SESSION_TTL))
    user.last_login_at = now()
    return token


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    session = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if session:
        session.revoked = True


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Sign in to continue.")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if not session or session.revoked or aware(session.expires_at) <= now():
        raise HTTPException(401, "Your session has ended. Sign in again.")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "This account is disabled.")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if not set(roles) & set(user.roles):
            raise HTTPException(403, f"This action needs one of these roles: {', '.join(ROLES[r] for r in roles)}.")
        return user
    return dependency


def can_access_aoi(user: User, aoi: str) -> bool:
    return not user.aois or aoi in user.aois


def audit(db: Session, actor: User | None, action: str, entity: str, entity_id, **details) -> None:
    db.add(AuditEvent(actor_id=actor.id if actor else None, action=action, entity=entity,
                      entity_id=str(entity_id), details=details))


def user_dict(user: User) -> dict:
    return {"id": str(user.id), "username": user.username, "display_name": user.display_name,
            "roles": user.roles, "aois": user.aois, "active": user.active}
