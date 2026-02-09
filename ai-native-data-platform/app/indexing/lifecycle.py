from __future__ import annotations

import os
import time
from dataclasses import dataclass

from app.core.observability import emit_event
from app.indexing.index_state import promote_target_to_active, set_target_embedding_version
from app.indexing.pipeline import IndexingConfig, build_manifest, run_manifest


@dataclass(frozen=True)
class ReindexResult:
    workspace_id: str
    old_active_version: str
    new_active_version: str
    indexed_docs: int
    indexed_chunks: int
    duration_s: float


def reindex_embeddings(
    *,
    workspace_id: str,
    target_embedding_version: str,
    limit: int | None = None,
    cfg: IndexingConfig | None = None,
) -> ReindexResult:
    """End-to-end embedding reindex with zero-downtime cutover.

    Operational semantics:
    1) Set workspace target embedding version (DB state).
    2) Run a bulk backfill that writes chunks tagged with target_embedding_version.
    3) Atomically promote target->active (bump index_epoch).

    Notes:
    - This design supports **shadow indexing** + **canary retrieval** by keeping
      target_embedding_version present while still serving active.
    - Consumers (retrieval) read active_embedding_version and ignore target until
      promotion.
    """
    cfg = cfg or IndexingConfig()

    # Persist the target for auditability and for multi-run resumability.
    set_target_embedding_version(workspace_id, target_embedding_version)
    emit_event("reindex_target_set", {"workspace_id": workspace_id, "target_embedding_version": target_embedding_version})

    # Override embedding version for the duration of the job.
    # We keep the override local to this process to avoid global impact.
    old = os.environ.get("EMBEDDING_VERSION")
    os.environ["EMBEDDING_VERSION"] = target_embedding_version

    t0 = time.time()
    try:
        manifest = build_manifest(workspace_id=workspace_id, limit=limit)
        stats = run_manifest(str(manifest), workspace_id=workspace_id, cfg=cfg)
    finally:
        if old is None:
            os.environ.pop("EMBEDDING_VERSION", None)
        else:
            os.environ["EMBEDDING_VERSION"] = old

    # Cutover.
    promote_target_to_active(workspace_id)
    emit_event("reindex_promoted", {"workspace_id": workspace_id, "new_active_embedding_version": target_embedding_version})

    return ReindexResult(
        workspace_id=workspace_id,
        old_active_version=stats.get("embedding_version", ""),
        new_active_version=target_embedding_version,
        indexed_docs=int(stats.get("indexed_docs") or 0),
        indexed_chunks=int(stats.get("indexed_chunks") or 0),
        duration_s=round(time.time() - t0, 3),
    )
