from __future__ import annotations

"""OpenSearch index management.

Index: ai_platform_chunks
  - BM25 lexical search on `content` (english analyser)
  - kNN vector search on `embedding` (HNSW, cosine, lucene engine)
  - Workspace-scoped via `workspace_id` keyword field

Design decisions:
  - Lucene engine chosen over NMSLIB/Faiss: single-node dev, no JNI overhead.
  - ef_search=128 balances recall vs latency for 384-dim vectors.
  - Index is idempotent: create_if_missing() is safe to call on every startup.
"""

import os

from app.core.config import settings
from app.core.observability import emit_event

EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))

INDEX_MAPPING = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 128,
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "analysis": {
            "analyzer": {
                "english_custom": {
                    "type": "english",
                }
            }
        },
    },
    "mappings": {
        "properties": {
            "workspace_id":       {"type": "keyword"},
            "document_id":        {"type": "keyword"},
            "chunk_id":           {"type": "keyword"},
            "chunk_index":        {"type": "integer"},
            "content":            {"type": "text", "analyzer": "english"},
            "source":             {"type": "keyword"},
            "embedding_version":  {"type": "keyword"},
            "metadata":           {"type": "object", "dynamic": True},
            "embedding": {
                "type": "knn_vector",
                "dimension": EMBED_DIM,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                    "parameters": {
                        "m": 16,
                        "ef_construction": 128,
                    },
                },
            },
        }
    },
}


def create_if_missing(client=None) -> bool:
    """Create the index if it does not exist. Returns True if created."""
    from app.opensearch.client import get_client
    os_client = client or get_client()
    index = settings.opensearch_index

    if os_client.indices.exists(index=index):
        return False

    os_client.indices.create(index=index, body=INDEX_MAPPING)
    emit_event("opensearch_index_created", {"index": index, "dim": EMBED_DIM})
    return True


def delete_index(client=None) -> None:
    """Delete the index — used in tests and reindex workflows."""
    from app.opensearch.client import get_client
    os_client = client or get_client()
    index = settings.opensearch_index
    if os_client.indices.exists(index=index):
        os_client.indices.delete(index=index)
        emit_event("opensearch_index_deleted", {"index": index})


def health(client=None) -> dict:
    """Return cluster health summary."""
    from app.opensearch.client import get_client
    os_client = client or get_client()
    return os_client.cluster.health(index=settings.opensearch_index)
