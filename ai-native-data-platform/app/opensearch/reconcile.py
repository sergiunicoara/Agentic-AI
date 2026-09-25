from __future__ import annotations

"""Postgres -> OpenSearch reconciliation.

Dual-write failures (`opensearch_dual_write_partial_failure` /
`opensearch_dual_write_failed`, emitted from app/ingestion/pipeline.py and
app/indexing/pipeline.py) are only ever logged — nothing consumes them — so a
chunk that fails to index in OpenSearch stays missing forever unless
something re-drives it. This module is that re-driver: it scans Postgres for
chunks that should be searchable and repairs any that OpenSearch is missing.

Scope (deliberately one-directional and conservative):

- Only repairs chunks under a workspace's *active* embedding_version (the
  only version actually served — see app/indexing/index_state.py). Chunks
  under an abandoned or in-progress (`target_embedding_version`) version are
  left alone; that divergence is expected, not a bug.
- Never deletes from OpenSearch. Postgres has no tombstone/soft-delete
  concept today, and app/opensearch/ingest.py::delete_by_document has zero
  callers and zero test coverage (see tasks/todo.md, "Explicitly deferred").
  Pruning OpenSearch orphans through that codepath here would be sneaking a
  delete feature in disguised as reconciliation. If document deletion ships
  later, orphan pruning belongs in its own reviewed change.
- Content drift — a Postgres row whose chunk_hash changed but whose
  OpenSearch copy never got the update — is out of scope too: detecting it
  needs chunk_hash in the OpenSearch _source, which the current schema
  (app/opensearch/ingest.py::_doc) doesn't carry. Flagged as a follow-up
  rather than silently growing this job's blast radius.

Why "missing in OpenSearch" is the only sanctioned drift direction: Postgres
always commits before the dual-write is attempted (both call sites push to
OpenSearch strictly after their `with workspace_session_scope(...)` block
exits), so under normal operation OpenSearch can only ever lag Postgres, not
get ahead of it.

Idempotent and safe to run concurrently with live ingestion: OpenSearch's
`_id` is deterministic (`doc_key`), so a repair can never duplicate a doc
that a concurrent ingest just wrote, and re-running this job over
already-healthy data is a no-op past the mget existence check.
"""

import time
from dataclasses import dataclass

from sqlalchemy import text

from app.core.config import settings
from app.core.observability import (
    RECONCILE_CHUNKS_REPAIRED,
    RECONCILE_RUNS,
    emit_event,
    persist_trace,
)
from app.data.db import read_session_scope, workspace_session_scope
from app.indexing.index_state import get_index_state
from app.opensearch.client import is_available
from app.opensearch.ingest import bulk_upsert, doc_key

MGET_BATCH_SIZE = 500
DEFAULT_SCAN_BATCH_SIZE = 500


@dataclass
class ReconciliationReport:
    workspace_id: str
    embedding_version: str
    checked: int = 0
    missing: int = 0
    repaired: int = 0
    repair_failed: int = 0
    skipped_reason: str | None = None
    duration_ms: int = 0

    def as_dict(self) -> dict:
        return {
            "workspace_id": self.workspace_id,
            "embedding_version": self.embedding_version,
            "checked": self.checked,
            "missing": self.missing,
            "repaired": self.repaired,
            "repair_failed": self.repair_failed,
            "skipped_reason": self.skipped_reason,
            "duration_ms": self.duration_ms,
        }


def _parse_vec_literal(raw: str) -> list[float]:
    """Inverse of the `_vec_literal` helper used on the write path
    (app/ingestion/pipeline.py, app/indexing/pipeline.py): pgvector's
    `::text` cast renders a vector as "[0.1,0.2,...]"."""
    return [float(x) for x in raw.strip("[]").split(",") if x]


def _missing_doc_keys(client, keys: list[str]) -> set[str]:
    """Return the subset of `keys` that do not exist in the OpenSearch index."""
    missing: set[str] = set()
    for i in range(0, len(keys), MGET_BATCH_SIZE):
        batch = keys[i : i + MGET_BATCH_SIZE]
        resp = client.mget(index=settings.opensearch_index, body={"ids": batch})
        for doc in resp.get("docs", []):
            if not doc.get("found"):
                missing.add(doc["_id"])
    return missing


def reconcile_workspace(workspace_id: str, *, batch_size: int = DEFAULT_SCAN_BATCH_SIZE) -> ReconciliationReport:
    """Scan one workspace's active-version chunks and repair any missing from
    OpenSearch. Returns a report; never raises for dual-write-shaped failures
    (OpenSearch down, a bad batch) — those are recorded as skipped/failed, not
    thrown, matching the existing dual-write error-handling convention.
    """
    t0 = time.time()
    active_version = get_index_state(workspace_id).active_embedding_version
    report = ReconciliationReport(workspace_id=workspace_id, embedding_version=active_version)

    if not settings.opensearch_dual_write or not settings.opensearch_url:
        report.skipped_reason = "opensearch_dual_write_disabled"
        RECONCILE_RUNS.labels(status="skipped").inc()
        return report
    if not is_available():
        report.skipped_reason = "opensearch_unavailable"
        RECONCILE_RUNS.labels(status="skipped").inc()
        return report

    from app.opensearch.client import get_client
    client = get_client()

    last_id = ""
    while True:
        with workspace_session_scope(workspace_id) as db:
            rows = db.execute(
                text(
                    """
                    SELECT id::text AS chunk_id, document_id::text AS document_id,
                           chunk_index, chunk_text, embedding::text AS embedding
                    FROM document_chunk
                    WHERE workspace_id = :ws
                      AND embedding_version = :ev
                      AND id::text > :after
                    ORDER BY id::text
                    LIMIT :lim
                    """
                ),
                {"ws": workspace_id, "ev": active_version, "after": last_id, "lim": batch_size},
            ).mappings().all()

        if not rows:
            break
        last_id = rows[-1]["chunk_id"]
        report.checked += len(rows)

        keys = [doc_key(r["document_id"], r["chunk_index"], active_version) for r in rows]
        try:
            missing_keys = _missing_doc_keys(client, keys)
        except Exception as e:
            emit_event("opensearch_reconcile_probe_failed", {"workspace_id": workspace_id, "error": str(e)})
            report.skipped_reason = "mget_failed"
            break

        if not missing_keys:
            continue

        to_repair = [
            {
                "chunk_id": r["chunk_id"],
                "document_id": r["document_id"],
                "workspace_id": workspace_id,
                "chunk_index": r["chunk_index"],
                "content": r["chunk_text"],
                "embedding": _parse_vec_literal(r["embedding"]),
                "embedding_version": active_version,
            }
            for r, key in zip(rows, keys)
            if key in missing_keys
        ]

        report.missing += len(to_repair)
        try:
            result = bulk_upsert(to_repair)
            report.repaired += result["indexed"]
            report.repair_failed += result["errors"]
            RECONCILE_CHUNKS_REPAIRED.inc(result["indexed"])
        except Exception as e:
            report.repair_failed += len(to_repair)
            emit_event("opensearch_reconcile_repair_failed", {
                "workspace_id": workspace_id, "count": len(to_repair), "error": str(e),
            })

    report.duration_ms = int((time.time() - t0) * 1000)
    RECONCILE_RUNS.labels(status="ok" if not report.skipped_reason else "error").inc()
    emit_event("opensearch_reconciliation_run", report.as_dict())
    persist_trace(
        trace_type="opensearch_reconciliation",
        workspace_id=workspace_id,
        body=report.as_dict(),
        latency_ms=report.duration_ms,
    )
    return report


def reconcile_all_workspaces(*, batch_size: int = DEFAULT_SCAN_BATCH_SIZE) -> list[ReconciliationReport]:
    """Reconcile every workspace. Intended as the cron/CLI entry point."""
    with read_session_scope() as db:
        ws_ids = [r[0] for r in db.execute(text("SELECT id FROM workspace ORDER BY id")).all()]
    return [reconcile_workspace(ws, batch_size=batch_size) for ws in ws_ids]
