from __future__ import annotations

"""OpenSearch ingestion helpers.

Supports:
  - Single-chunk upsert (used by the main ingestion pipeline)
  - Batch upsert (used by backfill scripts)
  - Idempotent: uses chunk_id as document _id so re-ingestion is safe
  - Retry: tenacity handles transient 429 / 503 from OpenSearch

Design decision: we use _id = chunk_id so that re-indexing a chunk is an
upsert, not a duplicate. This mirrors the ON CONFLICT behaviour in Postgres.
"""

import time
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.observability import emit_event


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
    from app.opensearch.index import create_if_missing

    client = get_client()
    create_if_missing(client)

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
        id=chunk_id,
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
    from opensearchpy.helpers import bulk  # type: ignore
    from app.opensearch.client import get_client
    from app.opensearch.index import create_if_missing

    if not chunks:
        return {"indexed": 0, "errors": 0}

    client = get_client()
    create_if_missing(client)

    actions = []
    for c in chunks:
        ev = c.get("embedding_version") or settings.embedding_version
        actions.append({
            "_op_type": "index",
            "_index": settings.opensearch_index,
            "_id": c["chunk_id"],
            "_source": _doc(
                chunk_id=c["chunk_id"],
                document_id=c["document_id"],
                workspace_id=c["workspace_id"],
                chunk_index=int(c.get("chunk_index", 0)),
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
