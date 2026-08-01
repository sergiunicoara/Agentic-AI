from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException
from sqlalchemy import text

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
    return x_workspace_id
