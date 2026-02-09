from __future__ import annotations

from fastapi import Header, HTTPException
from sqlalchemy import text

from app.data.db import read_session_scope


def require_workspace_key(
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    if not x_workspace_id or not x_api_key:
        raise HTTPException(401, "Missing X-Workspace-Id or X-API-Key")

    with read_session_scope() as db:
        row = db.execute(
            text("SELECT 1 FROM workspace_api_key WHERE workspace_id=:w AND api_key=:k"),
            {"w": x_workspace_id, "k": x_api_key},
        ).first()

    if not row:
        raise HTTPException(403, "Invalid workspace credentials")
    return x_workspace_id
