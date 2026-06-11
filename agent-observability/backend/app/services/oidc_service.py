"""OIDC Authorization Code Flow with PKCE helpers."""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any, Dict, Optional, Tuple

import httpx
from jose import JWTError, jwt

from app.config import settings

_JWKS_TTL_SECONDS = 3600  # providers rotate keys; never cache forever

_discovery_cache: Optional[Dict[str, Any]] = None
_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_fetched_at: float = 0.0


async def _discovery() -> Dict[str, Any]:
    global _discovery_cache
    if _discovery_cache is None:
        url = f"{settings.oidc_issuer_url.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, follow_redirects=True)
            r.raise_for_status()
            _discovery_cache = r.json()
    return _discovery_cache


async def get_jwks(force_refresh: bool = False) -> Dict[str, Any]:
    global _jwks_cache, _jwks_fetched_at
    expired = (time.monotonic() - _jwks_fetched_at) > _JWKS_TTL_SECONDS
    if _jwks_cache is None or expired or force_refresh:
        doc = await _discovery()
        async with httpx.AsyncClient() as client:
            r = await client.get(doc["jwks_uri"])
            r.raise_for_status()
            _jwks_cache = r.json()
            _jwks_fetched_at = time.monotonic()
    return _jwks_cache


def generate_pkce_pair() -> Tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256 method."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


async def get_authorization_url(state: str, code_challenge: str) -> str:
    doc = await _discovery()
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{doc['authorization_endpoint']}?{query}"


async def exchange_code(code: str, code_verifier: str) -> Dict[str, Any]:
    """Exchange authorization code + PKCE verifier for token response."""
    doc = await _discovery()
    data: Dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "client_id": settings.oidc_client_id,
        "code_verifier": code_verifier,
    }
    if settings.oidc_client_secret:
        data["client_secret"] = settings.oidc_client_secret

    async with httpx.AsyncClient() as client:
        r = await client.post(doc["token_endpoint"], data=data)
        r.raise_for_status()
        return r.json()


def _decode(id_token: str, jwks: Dict[str, Any], access_token: str) -> Dict[str, Any]:
    return jwt.decode(
        id_token,
        jwks,
        algorithms=["RS256", "ES256"],
        audience=settings.oidc_client_id,
        issuer=settings.oidc_issuer_url,
        access_token=access_token or None,
    )


async def validate_id_token(id_token: str, access_token: str = "") -> Dict[str, Any]:
    """Validate OIDC ID token signature via provider JWKS; return claims.

    Retries once with a force-refreshed JWKS so a provider key rotation
    mid-cache doesn't fail logins until restart.
    """
    jwks = await get_jwks()
    try:
        return _decode(id_token, jwks, access_token)
    except JWTError:
        jwks = await get_jwks(force_refresh=True)
        try:
            return _decode(id_token, jwks, access_token)
        except JWTError as exc:
            raise ValueError(f"Invalid ID token: {exc}") from exc
