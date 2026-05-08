"""Auth service: session token management + ABAC-aware FastAPI dependencies.

Login is now handled via OIDC (see routers/auth.py + services/oidc_service.py).
After OIDC validation the backend issues a short-lived internal JWT that carries
the user's ABAC attributes (role, department, clearance_level) so downstream
dependencies can enforce policy without extra DB round-trips.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.services.abac import check_action

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_redis: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


# --- Password helpers (kept for seed-admin bootstrap only) ---

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --- Internal session tokens ---

def create_session_token(user) -> str:
    """Issue an internal JWT after successful OIDC authentication.

    Embeds ABAC attributes so every request is self-contained.
    """
    jti = str(uuid.uuid4())
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "department": user.department or "",
        "clearance_level": user.clearance_level,
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


# --- FastAPI dependencies ---

_bearer = HTTPBearer()


async def _verified_payload(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if await is_revoked(payload.get("jti", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    token = credentials.credentials
    try:
        return decode_token(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_abac_action(action: str):
    """Dependency factory: verifies token + enforces ABAC action policy."""
    async def dependency(payload: dict = Depends(_verified_payload)) -> dict:
        if not check_action(payload, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action '{action}' not permitted for role '{payload.get('role')}'",
            )
        return payload
    return dependency


# Backward-compat alias so existing routers don't need a full rewrite yet
def require_role(minimum_role: str):
    """Map RBAC minimum_role to equivalent ABAC action check."""
    _role_to_action = {"viewer": "read", "developer": "write", "admin": "admin"}
    action = _role_to_action.get(minimum_role, "admin")
    return require_abac_action(action)
