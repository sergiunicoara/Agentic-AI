from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException
from sqlalchemy import text

from app.core.rate_limit import rate_limiter
from app.data.db import read_session_scope


def require_workspace_key(
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    if not x_workspace_id or not x_api_key:
        raise HTTPException(401, "Missing X-Workspace-Id or X-API-Key")

    api_key_hash = hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()
    with read_session_scope() as db:
        row = db.execute(
            text("SELECT api_key_hash FROM workspace_api_key WHERE workspace_id=:w"),
            {"w": x_workspace_id},
        ).mappings().first()

    if not row or not hmac.compare_digest(str(row["api_key_hash"]), api_key_hash):
        raise HTTPException(403, "Invalid workspace credentials")

    # Rate limit here, not in middleware keyed off the raw header: this runs
    # only after x_workspace_id/x_api_key have been validated against the
    # real credential, so a request with no valid key can't consume a real
    # workspace's quota by sending a forged X-Workspace-Id.
    if not rate_limiter.allow(x_workspace_id):
        raise HTTPException(429, "Rate limit exceeded")

    return x_workspace_id
