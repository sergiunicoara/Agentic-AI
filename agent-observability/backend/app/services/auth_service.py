"""Auth service: session token management + ABAC-aware FastAPI dependencies.

Login is handled via OIDC (see routers/auth.py + services/oidc_service.py).
After OIDC validation the backend issues a short-lived internal JWT that carries
the user's ABAC attributes (role, department, clearance_level) so downstream
dependencies can enforce policy without extra DB round-trips.

Revocation model:
- each token's jti is tracked under  session:{jti}  (per-key TTL, no shared-set
  expiry bug)
- active jtis per user are tracked under  user_jtis:{user_id}  so an admin can
  force-logout a user immediately (e.g. after a role/clearance downgrade)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.services.abac import check_action

_redis: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


# --- Internal session tokens ---

def _session_ttl_seconds() -> int:
    return settings.jwt_expire_minutes * 60


async def issue_session_token(user) -> str:
    """Issue an internal JWT after successful OIDC authentication.

    Embeds ABAC attributes so every request is self-contained, and records the
    jti against the user so sessions can be force-revoked.
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

    r = get_redis()
    key = f"user_jtis:{user.id}"
    await r.sadd(key, jti)
    await r.expire(key, _session_ttl_seconds())

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


async def revoke_token(jti: str) -> None:
    """Revoke a single session. Per-jti key so TTLs are independent."""
    r = get_redis()
    await r.set(f"revoked:{jti}", "1", ex=_session_ttl_seconds())


async def revoke_user_sessions(user_id: str) -> int:
    """Force-logout every active session of a user. Returns count revoked."""
    r = get_redis()
    key = f"user_jtis:{user_id}"
    jtis = await r.smembers(key)
    for jti in jtis:
        await r.set(f"revoked:{jti}", "1", ex=_session_ttl_seconds())
    await r.delete(key)
    return len(jtis)


async def is_revoked(jti: str) -> bool:
    r = get_redis()
    return bool(await r.exists(f"revoked:{jti}"))


# --- FastAPI dependencies ---

_bearer = HTTPBearer()


async def verified_payload(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """Decode + revocation-check. The only correct way to authenticate a request."""
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if await is_revoked(payload.get("jti", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    return payload


# Every consumer gets the revocation check — no decode-only path remains.
get_current_user = verified_payload


def require_abac_action(action: str):
    """Dependency factory: verifies token + enforces ABAC action policy."""
    async def dependency(payload: dict = Depends(verified_payload)) -> dict:
        if not check_action(payload, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action '{action}' not permitted for role '{payload.get('role')}'",
            )
        return payload
    return dependency


def require_role(minimum_role: str):
    """Map RBAC minimum_role to equivalent ABAC action check."""
    _role_to_action = {"viewer": "read", "developer": "write", "admin": "admin"}
    action = _role_to_action.get(minimum_role, "admin")
    return require_abac_action(action)
