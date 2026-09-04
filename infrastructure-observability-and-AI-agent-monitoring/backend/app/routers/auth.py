"""OIDC Authorization Code Flow with PKCE.

GET  /auth/authorize          → generate PKCE pair, store verifier in Redis,
                                return redirect URL to OIDC provider
POST /auth/callback           → exchange code + verifier, validate ID token,
                                JIT-provision user, return session token
POST /auth/logout             → revoke session token
"""
from __future__ import annotations

import logging
import re
import secrets
import uuid

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.services.auth_service import (
    decode_token,
    get_redis,
    issue_session_token,
    revoke_token,
)
from app.services.oidc_service import (
    exchange_code,
    get_authorization_url,
    validate_id_token,
)
from app.services.request_context import client_ip

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer()

_PKCE_TTL = 300          # seconds — PKCE verifier validity window
_AUTHORIZE_RATE = 10     # max /authorize calls per IP per minute

# RFC 7636 §4.1: code_challenge is base64url of a SHA-256 digest. Anything else
# is rejected here rather than concatenated into the provider's authorize URL.
_CODE_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


async def _rate_limit(request: Request, bucket: str, limit: int) -> None:
    """Fixed-window per-IP rate limit backed by Redis."""
    ip = client_ip(request) or "unknown"
    r = get_redis()
    key = f"rl:{bucket}:{ip}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 60)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, slow down",
        )


# ---------------------------------------------------------------------------
# Step 1: initiate OIDC flow
# ---------------------------------------------------------------------------

class AuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


@router.get("/authorize", response_model=AuthorizeResponse)
async def authorize(code_challenge: str, request: Request):
    """Return the OIDC authorization URL.

    The frontend generates the PKCE pair and sends the challenge here.
    The backend stores the state for CSRF validation; the frontend retains
    the verifier and sends it back in /callback.
    """
    await _rate_limit(request, "authorize", _AUTHORIZE_RATE)
    if not _CODE_CHALLENGE_RE.match(code_challenge):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_challenge must be a base64url-encoded S256 challenge",
        )
    state = secrets.token_urlsafe(16)
    r = get_redis()
    await r.set(f"state:{state}", "valid", ex=_PKCE_TTL)

    url = await get_authorization_url(state=state, code_challenge=code_challenge)
    return AuthorizeResponse(authorization_url=url, state=state)


# ---------------------------------------------------------------------------
# Step 2: handle callback — exchange code for session token
# ---------------------------------------------------------------------------

class CallbackRequest(BaseModel):
    code: str
    state: str
    code_verifier: str  # frontend sends back the verifier it generated


class SessionTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/callback", response_model=SessionTokenResponse)
async def callback(body: CallbackRequest, db: AsyncSession = Depends(get_db)):
    """Exchange OIDC authorization code for an internal session token."""
    r = get_redis()
    if not await r.get(f"state:{body.state}"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired state")
    await r.delete(f"state:{body.state}")

    code_verifier = body.code_verifier
    if not code_verifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code_verifier")

    try:
        token_response = await exchange_code(code=body.code, code_verifier=code_verifier)
        claims = await validate_id_token(
            token_response["id_token"],
            access_token=token_response.get("access_token", ""),
        )
    except Exception as exc:
        logger.error("OIDC callback failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    oidc_sub: str = claims["sub"]
    email: str = claims.get("email", "")
    if not email or not claims.get("email_verified", False):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC email is not verified")

    # JIT provision: create user on first login, or fetch existing
    result = await db.execute(select(User).where(User.oidc_sub == oidc_sub))
    user = result.scalar_one_or_none()

    if user is None:
        # Also check by email in case user was pre-created (seed admin, etc.)
        result2 = await db.execute(select(User).where(User.email == email))
        user = result2.scalar_one_or_none()

    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            oidc_sub=oidc_sub,
            role="viewer",
            clearance_level=0,
        )
        db.add(user)
    else:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")
        # Bind OIDC sub to existing user
        user.oidc_sub = oidc_sub

    await db.commit()
    await db.refresh(user)

    return SessionTokenResponse(access_token=await issue_session_token(user))


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        payload = decode_token(credentials.credentials)
        await revoke_token(payload["jti"])
    except JWTError:
        # Already-invalid token: nothing to revoke, logout is still a success.
        pass
    except Exception:
        # Revocation genuinely failed (e.g. Redis down) — the session is still
        # live, so say so instead of reporting a logout that did not happen.
        logger.exception("Failed to revoke session token on logout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not revoke session, try again",
        )
    return {"detail": "Logged out"}
