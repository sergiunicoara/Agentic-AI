from __future__ import annotations

"""OpenSearch ingestion helpers.

Supports:
  - Single-chunk upsert (used by the main ingestion pipeline)
  - Batch upsert (used by the pipeline post-commit and backfill scripts)
  - Idempotent: the OpenSearch _id is deterministic —
    "{document_id}:{chunk_index}:{embedding_version}" — so re-ingesting a
    document overwrites in place instead of duplicating. This mirrors the
    Postgres conflict key ON CONFLICT (document_id, chunk_index,
    embedding_version), not the chunk uuid (which changes on every run).
  - Retry: tenacity handles transient 429 / 503 from OpenSearch.

The _source still carries the Postgres chunk uuid in `chunk_id`, so retrieval
results reference the same ids as the pgvector backend.
"""

import threading
import time
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.observability import emit_event

# One indices.exists round-trip per process, not per chunk.
_index_ready = False
_index_lock = threading.Lock()


def _ensure_index(client) -> None:
    global _index_ready
    if _index_ready:
        return
    with _index_lock:
        if _index_ready:
            return
        from app.opensearch.index import create_if_missing
        create_if_missing(client)
        _index_ready = True


def reset_index_cache() -> None:
    """Reset the index-exists cache — used in tests and reindex workflows."""
    global _index_ready
    _index_ready = False


def doc_key(document_id: str, chunk_index: int, embedding_version: str) -> str:
    """Deterministic OpenSearch _id matching the Postgres conflict key."""
    return f"{document_id}:{chunk_index}:{embedding_version}"


def _doc(
    *,
    chunk_id: str,
    document_id: str,
    workspace_id: str,
    chunk_index: int,
    content: str,
    embedding: list[float],
    source: str = "upload",
    embedding_version: str = "v1",
    metadata: dict[str, Any] | None = None,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "workspace_id": workspace_id,
        "chunk_index": chunk_index,
        "content": content,
        "source": source,
        "embedding_version": embedding_version,
        "metadata": metadata or {},
        "embedding": embedding,
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=5))
def upsert_chunk(
    *,
    chunk_id: str,
    document_id: str,
    workspace_id: str,
    chunk_index: int,
    content: str,
    embedding: list[float],
    source: str = "upload",
    embedding_version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Upsert a single chunk into OpenSearch. Safe to call repeatedly."""
    from app.opensearch.client import get_client

    client = get_client()
    _ensure_index(client)

    ev = embedding_version or settings.embedding_version
    body = _doc(
        chunk_id=chunk_id,
        document_id=document_id,
        workspace_id=workspace_id,
        chunk_index=chunk_index,
        content=content,
        embedding=embedding,
        source=source,
        embedding_version=ev,
        metadata=metadata,
    )
    client.index(
        index=settings.opensearch_index,
        id=doc_key(document_id, chunk_index, ev),
        body=body,
        refresh="false",   # async refresh — don't block ingestion
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=5))
def bulk_upsert(chunks: list[dict]) -> dict[str, int]:
    """Bulk upsert a list of chunk dicts.

    Each dict must have: chunk_id, document_id, workspace_id, chunk_index,
    content, embedding. Optional: source, embedding_version, metadata.

    Returns {"indexed": N, "errors": M}.
    """
    # Guard before any opensearchpy import so an empty call needs no library.
    if not chunks:
        return {"indexed": 0, "errors": 0}

    from opensearchpy.helpers import bulk  # type: ignore
    from app.opensearch.client import get_client

    client = get_client()
    _ensure_index(client)

    actions = []
    for c in chunks:
        ev = c.get("embedding_version") or settings.embedding_version
        idx = int(c.get("chunk_index", 0))
        actions.append({
            "_op_type": "index",
            "_index": settings.opensearch_index,
            "_id": doc_key(c["document_id"], idx, ev),
            "_source": _doc(
                chunk_id=c["chunk_id"],
                document_id=c["document_id"],
                workspace_id=c["workspace_id"],
                chunk_index=idx,
                content=c["content"],
                embedding=c["embedding"],
                source=c.get("source", "upload"),
                embedding_version=ev,
                metadata=c.get("metadata") or {},
            ),
        })

    t0 = time.time()
    success, errors = bulk(client, actions, chunk_size=500, raise_on_error=False)
    elapsed = int((time.time() - t0) * 1000)

    error_count = len(errors) if isinstance(errors, list) else int(errors)
    emit_event("opensearch_bulk_upsert", {
        "indexed": success,
        "errors": error_count,
        "latency_ms": elapsed,
    })
    return {"indexed": success, "errors": error_count}


def delete_by_document(document_id: str, workspace_id: str) -> int:
    """Delete all chunks for a document. Used during re-ingestion."""
    from app.opensearch.client import get_client
    client = get_client()
    resp = client.delete_by_query(
        index=settings.opensearch_index,
        body={
            "query": {
                "bool": {
                    "must": [
                        {"term": {"document_id": document_id}},
                        {"term": {"workspace_id": workspace_id}},
                    ]
                }
            }
        },
        refresh=True,
    )
    deleted = resp.get("deleted", 0)
    emit_event("opensearch_delete_by_document", {"document_id": document_id, "deleted": deleted})
    return int(deleted)
