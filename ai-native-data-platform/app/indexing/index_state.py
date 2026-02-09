from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import text

from app.core.config import settings
from app.data.db import read_session_scope, write_session_scope


@dataclass(frozen=True)
class WorkspaceIndexState:
    workspace_id: str
    active_embedding_version: str
    target_embedding_version: str | None
    index_epoch: int
    updated_at_s: float


# Simple in-process cache (per API worker).
# Production would use Redis/sidecar; this is enough to avoid a DB read per request.
_state_cache: dict[str, WorkspaceIndexState] = {}
_state_cache_expiry: dict[str, float] = {}


def _table_exists(db) -> bool:
    try:
        r = db.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema='public' AND table_name='workspace_index_state'
                """
            )
        ).first()
        return bool(r)
    except Exception:
        return False


def get_index_state(workspace_id: str, *, ttl_s: int = 10) -> WorkspaceIndexState:
    now = time.time()
    exp = _state_cache_expiry.get(workspace_id, 0.0)
    if now < exp and workspace_id in _state_cache:
        return _state_cache[workspace_id]

    with read_session_scope(region=settings.region) as db:
        if not _table_exists(db):
            st = WorkspaceIndexState(
                workspace_id=workspace_id,
                active_embedding_version=settings.embedding_version,
                target_embedding_version=None,
                index_epoch=0,
                updated_at_s=now,
            )
            _state_cache[workspace_id] = st
            _state_cache_expiry[workspace_id] = now + ttl_s
            return st

        row = db.execute(
            text(
                """
                SELECT workspace_id::text AS workspace_id,
                       active_embedding_version,
                       target_embedding_version,
                       index_epoch,
                       EXTRACT(EPOCH FROM updated_at) AS updated_at_s
                FROM workspace_index_state
                WHERE workspace_id=:w
                """
            ),
            {"w": workspace_id},
        ).mappings().first()

    if not row:
        st = WorkspaceIndexState(
            workspace_id=workspace_id,
            active_embedding_version=settings.embedding_version,
            target_embedding_version=None,
            index_epoch=0,
            updated_at_s=now,
        )
    else:
        st = WorkspaceIndexState(
            workspace_id=row["workspace_id"],
            active_embedding_version=row.get("active_embedding_version") or settings.embedding_version,
            target_embedding_version=row.get("target_embedding_version"),
            index_epoch=int(row.get("index_epoch") or 0),
            updated_at_s=float(row.get("updated_at_s") or now),
        )

    _state_cache[workspace_id] = st
    _state_cache_expiry[workspace_id] = now + ttl_s
    return st


def set_target_embedding_version(workspace_id: str, target_version: str) -> None:
    with write_session_scope() as db:
        db.execute(
            text(
                """
                INSERT INTO workspace_index_state (workspace_id, active_embedding_version, target_embedding_version, index_epoch)
                VALUES (:w, :active, :target, 0)
                ON CONFLICT (workspace_id)
                DO UPDATE SET target_embedding_version=:target, updated_at=NOW()
                """
            ),
            {"w": workspace_id, "active": settings.embedding_version, "target": target_version},
        )


def promote_target_to_active(workspace_id: str) -> None:
    """Atomically cut over to target embedding version and bump index_epoch.

    This is the operational primitive for *zero-downtime reindexing*.
    Retrieval reads active_embedding_version and uses index_epoch for strict consistency mode.
    """
    with write_session_scope() as db:
        db.execute(
            text(
                """
                UPDATE workspace_index_state
                SET active_embedding_version = COALESCE(target_embedding_version, active_embedding_version),
                    target_embedding_version = NULL,
                    index_epoch = index_epoch + 1,
                    updated_at = NOW()
                WHERE workspace_id=:w
                """
            ),
            {"w": workspace_id},
        )

    # Drop cache to avoid stale reads.
    _state_cache.pop(workspace_id, None)
    _state_cache_expiry.pop(workspace_id, None)


def clear_target_embedding_version(workspace_id: str) -> None:
    with write_session_scope() as db:
        db.execute(
            text(
                """
                UPDATE workspace_index_state
                SET target_embedding_version = NULL,
                    updated_at = NOW()
                WHERE workspace_id=:w
                """
            ),
            {"w": workspace_id},
        )
    _state_cache.pop(workspace_id, None)
    _state_cache_expiry.pop(workspace_id, None)


def set_active_embedding_version(workspace_id: str, active_version: str) -> None:
    """Force active embedding version (rollback primitive).

    This is intended for operational rollback after a bad cutover.
    """
    with write_session_scope() as db:
        db.execute(
            text(
                """
                INSERT INTO workspace_index_state (workspace_id, active_embedding_version, target_embedding_version, index_epoch)
                VALUES (:w, :active, NULL, 0)
                ON CONFLICT (workspace_id)
                DO UPDATE SET active_embedding_version=:active, target_embedding_version=NULL, updated_at=NOW()
                """
            ),
            {"w": workspace_id, "active": active_version},
        )
    _state_cache.pop(workspace_id, None)
    _state_cache_expiry.pop(workspace_id, None)
