"""
Bearer-token auth shared by the JSON-RPC endpoint, its SSE streaming
methods, the legacy REST wrappers, and the `/ws/scan` WebSocket. Opt-in:
set SENTINEL_A2A_TOKEN to require it; unset (or empty) means these
endpoints stay open (matching prior behavior for local/demo use).

Uses hmac.compare_digest instead of `==` so the comparison is
constant-time regardless of where the strings first differ. Both sides
are compared as UTF-8 bytes: compare_digest raises TypeError on non-ASCII
`str` input, which would otherwise turn a junk header into a 500.
"""
import hmac
import os

from fastapi import Header, HTTPException

A2A_TOKEN = os.environ.get("SENTINEL_A2A_TOKEN") or None


def token_required() -> bool:
    return A2A_TOKEN is not None


def token_matches(presented: str | None) -> bool:
    """True when `presented` is the configured token (raw, no "Bearer " prefix),
    or when no token is configured at all."""
    if A2A_TOKEN is None:
        return True
    if presented is None:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), A2A_TOKEN.encode("utf-8"))


def bearer_value(authorization: str | None) -> str | None:
    """Extract the credential from an `Authorization: Bearer <token>` header."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip()


def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    if A2A_TOKEN is None:
        return
    if not token_matches(bearer_value(authorization)):
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token")
