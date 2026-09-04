import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import AuditLog, User
from app.services.auth_service import require_role, revoke_user_sessions

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_dep = Depends(require_role("admin"))

_VALID_ROLES = ("admin", "developer", "viewer")
_VALID_CLEARANCE = (0, 1, 2)

# Deliberately permissive: identity is proven by the OIDC provider, this only
# rejects values that cannot be an address at all.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class UserCreate(BaseModel):
    """Pre-provision a user before their first OIDC login.

    No password — identity is proven by the OIDC provider; the account is
    matched by email and bound to the provider's sub claim on first login.
    """
    email: str
    role: str = "viewer"
    clearance_level: int = 0
    department: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("must be a valid email address")
        return v


class UserUpdate(BaseModel):
    role: Optional[str] = None
    clearance_level: Optional[int] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    clearance_level: int
    department: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[str]
    method: str
    path: str
    status_code: int
    ip_address: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


@router.get("/users", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _user: dict = _admin_dep,
):
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    _user: dict = _admin_dep,
):
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if body.clearance_level not in _VALID_CLEARANCE:
        raise HTTPException(status_code=400, detail="Invalid clearance level")
    existing = await db.execute(select(User.id).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="A user with that email already exists")

    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        role=body.role,
        clearance_level=body.clearance_level,
        department=body.department,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:                       # lost the race against a concurrent create
        await db.rollback()
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin_user: dict = _admin_dep,
):
    """Update ABAC attributes. All active sessions of the user are revoked so
    the change takes effect immediately instead of at token expiry."""
    if body.role is not None and body.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if body.clearance_level is not None and body.clearance_level not in _VALID_CLEARANCE:
        raise HTTPException(status_code=400, detail="Invalid clearance level")

    # Admin access is only grantable by an admin, so an admin who demotes or
    # deactivates themselves can lock everyone out of /admin permanently.
    if user_id == str(admin_user.get("sub")):
        if body.role is not None and body.role != "admin":
            raise HTTPException(status_code=400, detail="Cannot remove your own admin role")
        if body.is_active is False:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.role is not None:
        user.role = body.role
    if body.clearance_level is not None:
        user.clearance_level = body.clearance_level
    if body.department is not None:
        user.department = body.department or None
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.commit()
    await db.refresh(user)
    await revoke_user_sessions(user_id)
    return user


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_sessions(
    user_id: str,
    _user: dict = _admin_dep,
):
    """Force-logout: revoke every active session token of a user."""
    count = await revoke_user_sessions(user_id)
    return {"user_id": user_id, "revoked_sessions": count}


@router.get("/audit", response_model=list[AuditLogOut])
async def get_audit_log(
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _user: dict = _admin_dep,
):
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    logs = result.scalars().all()
    return [
        AuditLogOut(
            id=log.id,
            user_id=log.user_id,
            method=log.method,
            path=log.path,
            status_code=log.status_code,
            ip_address=log.ip_address,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]
