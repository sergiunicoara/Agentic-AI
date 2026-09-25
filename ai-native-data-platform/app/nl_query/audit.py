from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from app.core.observability import emit_event
from app.data.db import workspace_session_scope


def write_audit_log(
    *,
    workspace_id: str,
    nl_query: str,
    generated_sql: str,
    params: dict,
    row_count: int,
    latency_ms: int,
    error: str | None,
) -> None:
    """Persist NL query audit record. Best-effort — never raises."""
    # Strip the internal workspace_id param; it's already a column in the log.
    safe_params = {k: v for k, v in params.items() if k != "_workspace_id"}

    try:
        with workspace_session_scope(workspace_id, write=True) as db:
            db.execute(
                text(
                    """
                    INSERT INTO nl_query_audit_log
                        (id, workspace_id, nl_query, generated_sql, params,
                         row_count, latency_ms, error)
                    VALUES
                        (:id, :workspace_id, :nl_query, :generated_sql,
                         CAST(:params AS jsonb), :row_count, :latency_ms, :error)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "nl_query": nl_query,
                    "generated_sql": generated_sql,
                    "params": json.dumps(safe_params),
                    "row_count": row_count,
                    "latency_ms": latency_ms,
                    "error": error,
                },
            )
    except Exception as e:
        # Best-effort by design, but this is the compliance audit trail for
        # every NL->SQL query — a silent swallow here previously hid a real
        # bug (an invalid bind expression) for the life of this module.
        emit_event("nl_query_audit_write_failed", {"workspace_id": workspace_id, "error": str(e)})
