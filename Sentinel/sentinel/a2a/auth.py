"""
Bearer-token auth shared by the JSON-RPC endpoint, its SSE streaming
methods, and the legacy REST wrappers. Opt-in: set SENTINEL_A2A_TOKEN to
require it; unset means these endpoints stay open (matching prior
behavior for local/demo use).

Uses hmac.compare_digest instead of `==` so the comparison is
constant-time regardless of where the strings first differ.
"""
import hmac
import os

from fastapi import Header, HTTPException

A2A_TOKEN = os.environ.get("SENTINEL_A2A_TOKEN")


def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    if A2A_TOKEN is None:
        return
    expected = f"Bearer {A2A_TOKEN}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token")
