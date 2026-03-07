import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import AuditLog, User
from app.services.auth_service import hash_password, require_role

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_dep = Depends(require_role("admin"))


class UserCreate(BaseModel):
    email: str
    password: str
    role: str = "viewer"


class UserOut(BaseModel):
    id: str
    email: str
    role: str
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
    if body.role not in ("admin", "developer", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/role")
async def update_role(
    user_id: str,
    role: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = _admin_dep,
):
    if role not in ("admin", "developer", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = role
    await db.commit()
    return {"id": user_id, "role": role}


@router.get("/audit", response_model=list[AuditLogOut])
async def get_audit_log(
    limit: int = 100,
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
