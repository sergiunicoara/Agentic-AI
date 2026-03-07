import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis.asyncio as aioredis
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_redis: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


# --- Password helpers ---

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --- JWT ---

def create_access_token(user: User) -> str:
    jti = str(uuid.uuid4())
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "jti": jti,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


async def revoke_token(jti: str) -> None:
    r = get_redis()
    await r.sadd("revoked_jtis", jti)
    await r.expire("revoked_jtis", settings.jwt_expire_minutes * 60)


async def is_revoked(jti: str) -> bool:
    r = get_redis()
    return bool(await r.sismember("revoked_jtis", jti))


# --- DB helpers ---

async def get_user_by_email(email: str, db: AsyncSession) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def authenticate_user(email: str, password: str, db: AsyncSession) -> Optional[User]:
    user = await get_user_by_email(email, db)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


# --- RBAC dependency factory ---

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer()

ROLE_HIERARCHY = {"viewer": 0, "developer": 1, "admin": 2}


def require_role(minimum_role: str):
    async def dependency(
        credentials: HTTPAuthorizationCredentials = Depends(_bearer),
        db: AsyncSession = Depends(lambda: None),  # injected below
    ) -> dict:
        token = credentials.credentials
        try:
            payload = decode_token(token)
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        if await is_revoked(payload.get("jti", "")):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

        user_role = payload.get("role", "viewer")
        if ROLE_HIERARCHY.get(user_role, -1) < ROLE_HIERARCHY.get(minimum_role, 999):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

        return payload

    return dependency


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    token = credentials.credentials
    try:
        return decode_token(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
