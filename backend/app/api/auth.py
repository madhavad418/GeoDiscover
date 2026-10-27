from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import (
    ROLES, SESSION_COOKIE, SESSION_TTL, audit, check_login_rate, clear_login_failures, create_session, current_user,
    hash_password, record_login_failure, require_roles, revoke_session, user_dict, validate_password, validate_roles,
    verify_password,
)
from ..db import get_db
from ..models.platform import User
from ..services.customer_import import AOIS

router = APIRouter(tags=["auth & users"])


class Login(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=200)


@router.post("/auth/login")
def login(body: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    username = body.username.strip().lower()
    key = f"{username}|{request.client.host if request.client else ''}"
    check_login_rate(key)
    user = db.scalar(select(User).where(User.username == username))
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        record_login_failure(key)
        raise HTTPException(401, "Username or password is incorrect.")
    clear_login_failures(key)
    token = create_session(db, user)
    audit(db, user, "login", "user", user.id)
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, max_age=int(SESSION_TTL.total_seconds()), httponly=True,
                        samesite="lax", secure=request.url.scheme == "https", path="/")
    return user_dict(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    revoke_session(db, request.cookies.get(SESSION_COOKIE))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {**user_dict(user), "role_names": {r: ROLES[r] for r in user.roles}}


@router.get("/auth/roles")
def roles():
    return {"roles": ROLES, "aois": list(AOIS)}


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._@+-]+$")  # plain names or email addresses
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(max_length=200)
    roles: list[str]
    aois: list[str] = []


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)
    roles: list[str] | None = None
    aois: list[str] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=200)


def _check_aois(aois):
    unknown = set(aois) - set(AOIS)
    if unknown:
        raise HTTPException(422, f"Unknown AOI: {', '.join(sorted(unknown))}")
    return sorted(set(aois))


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles("ops_manager", "qc_lead"))):
    return [user_dict(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles("ops_manager"))):
    username = body.username.lower()
    if db.scalar(select(func.count()).select_from(User).where(User.username == username)):
        raise HTTPException(409, "That username is taken.")
    validate_password(body.password)
    user = User(username=username, display_name=body.display_name.strip(), password_hash=hash_password(body.password),
                roles=validate_roles(body.roles), aois=_check_aois(body.aois))
    db.add(user)
    db.flush()
    audit(db, actor, "create_user", "user", user.id, roles=user.roles, aois=user.aois)
    db.commit()
    return user_dict(user)


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, db: Session = Depends(get_db),
                actor: User = Depends(require_roles("ops_manager"))):
    user = db.scalar(select(User).where(User.id == _uuid(user_id)))
    if not user:
        raise HTTPException(404, "User not found")
    changes = {}
    if body.display_name is not None:
        user.display_name = changes["display_name"] = body.display_name.strip()
    if body.roles is not None:
        user.roles = changes["roles"] = validate_roles(body.roles)
    if body.aois is not None:
        user.aois = changes["aois"] = _check_aois(body.aois)
    if body.active is not None:
        if user.id == actor.id and not body.active:
            raise HTTPException(422, "You can't disable your own account.")
        user.active = changes["active"] = body.active
    if body.password:
        validate_password(body.password)
        user.password_hash = hash_password(body.password)
        changes["password"] = "reset"
    audit(db, actor, "update_user", "user", user.id, **changes)
    db.commit()
    return user_dict(user)


def _uuid(value):
    from uuid import UUID
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(404, "User not found") from None
