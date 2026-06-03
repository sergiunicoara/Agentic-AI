from __future__ import annotations

"""OpenSearch retrieval adapters.

Three concrete retrievers, all conforming to the Retriever Protocol:

  OpenSearchBM25Retriever   — lexical (BM25) search via match query
  OpenSearchVectorRetriever — dense search via kNN query
  OpenSearchHybridRetriever — runs both, fuses with RRF in Python

Design decisions:
  - RRF fusion in Python (not OpenSearch neural pipeline) keeps the code
    portable across OpenSearch versions and requires no ML Commons setup.
  - workspace_id is enforced as a term filter on every query — never optional.
  - Scores from BM25 and kNN are not directly comparable, but RRF rank-based
    fusion makes this irrelevant: only rank order matters.
  - The `database_url` parameter is accepted but ignored (OpenSearch URL comes
    from settings) so the interface matches the Retriever Protocol used by the
    existing RetrievalPipeline.
"""

from dataclasses import dataclass, field
from prometheus_client import Histogram

from app.core.config import settings
from app.schemas import RetrievedChunk

# ── Prometheus metrics ──────────────────────────────────────────────────────

OS_BM25_LATENCY = Histogram(
    "opensearch_bm25_latency_seconds",
    "OpenSearch BM25 retrieval latency",
)
OS_VECTOR_LATENCY = Histogram(
    "opensearch_vector_latency_seconds",
    "OpenSearch kNN vector retrieval latency",
)
OS_HYBRID_LATENCY = Histogram(
    "opensearch_hybrid_latency_seconds",
    "OpenSearch hybrid retrieval latency (BM25 + vector + RRF)",
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _hit_to_chunk(hit: dict, retriever: str) -> RetrievedChunk:
    src = hit["_source"]
    return RetrievedChunk(
        id=src.get("chunk_id", hit["_id"]),
        document_id=src.get("document_id", ""),
        chunk_index=src.get("chunk_index"),
        text=src.get("content", ""),
        score=float(hit.get("_score") or 0.0),
        modality="text",
        meta={
            "retriever": retriever,
            "embedding_version": src.get("embedding_version", ""),
            "source": src.get("source", ""),
        },
    )


def _rrf_fuse(
    bm25_hits: list[RetrievedChunk],
    vec_hits: list[RetrievedChunk],
    *,
    k: int,
    rrf_k: int,
    bm25_boost: float,
    vector_boost: float,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion over BM25 and vector result lists."""
    scores: dict[str, float] = {}
    by_id: dict[str, RetrievedChunk] = {}

    for rank, chunk in enumerate(bm25_hits, start=1):
        scores[chunk.id] = scores.get(chunk.id, 0.0) + bm25_boost / (rrf_k + rank)
        by_id.setdefault(chunk.id, chunk)

    for rank, chunk in enumerate(vec_hits, start=1):
        scores[chunk.id] = scores.get(chunk.id, 0.0) + vector_boost / (rrf_k + rank)
        by_id.setdefault(chunk.id, chunk)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out: list[RetrievedChunk] = []
    for cid, s in ranked[:k]:
        c = by_id[cid]
        c.score = s
        out.append(c)
    return out


# ── BM25 Retriever ──────────────────────────────────────────────────────────

@dataclass
class OpenSearchBM25Retriever:
    """Lexical BM25 retrieval using OpenSearch match query."""

    def retrieve(
        self,
        workspace_id: str,
        query: str,
        k: int,
        *,
        query_vec: list[float] | None = None,
        database_url: str | None = None,
        embedding_version: str | None = None,
    ) -> list[RetrievedChunk]:
        from app.opensearch.client import get_client
        import time

        client = get_client()
        ev = embedding_version or settings.embedding_version

        body = {
            "size": k,
            "_source": {"excludes": ["embedding"]},
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "content": {
                                    "query": query,
                                    "analyzer": "english",
                                    "operator": "or",
                                }
                            }
                        }
                    ],
                    "filter": [
                        {"term": {"workspace_id": workspace_id}},
                        {"term": {"embedding_version": ev}},
                    ],
                }
            },
        }

        t0 = time.time()
        resp = client.search(index=settings.opensearch_index, body=body)
        OS_BM25_LATENCY.observe(time.time() - t0)

        return [_hit_to_chunk(h, "opensearch_bm25") for h in resp["hits"]["hits"]]


# ── Vector (kNN) Retriever ──────────────────────────────────────────────────

@dataclass
class OpenSearchVectorRetriever:
    """Dense kNN retrieval using OpenSearch knn_vector field."""

    def retrieve(
        self,
        workspace_id: str,
        query: str,
        k: int,
        *,
        query_vec: list[float] | None = None,
        database_url: str | None = None,
        embedding_version: str | None = None,
    ) -> list[RetrievedChunk]:
        from app.opensearch.client import get_client
        from app.providers.embeddings import embed
        import time

        client = get_client()
        ev = embedding_version or settings.embedding_version
        vec = query_vec or embed(query)

        body = {
            "size": k,
            "_source": {"excludes": ["embedding"]},
            "query": {
                "knn": {
                    "embedding": {
                        "vector": vec,
                        "k": k,
                        "filter": {
                            "bool": {
                                "must": [
                                    {"term": {"workspace_id": workspace_id}},
                                    {"term": {"embedding_version": ev}},
                                ]
                            }
                        },
                    }
                }
            },
        }

        t0 = time.time()
        resp = client.search(index=settings.opensearch_index, body=body)
        OS_VECTOR_LATENCY.observe(time.time() - t0)

        return [_hit_to_chunk(h, "opensearch_vector") for h in resp["hits"]["hits"]]


# ── Hybrid Retriever ─────────────────────────────────────────────────────────

@dataclass
class OpenSearchHybridRetriever:
    """Hybrid retrieval: BM25 + kNN fused with RRF.

    Runs both queries in parallel threads, then applies Reciprocal Rank Fusion.
    RRF is computed in Python so the implementation is version-independent —
    no ML Commons pipeline or search pipeline configuration required.
    """

    rrf_k: int = field(default_factory=lambda: settings.opensearch_rrf_k)
    bm25_boost: float = field(default_factory=lambda: settings.opensearch_bm25_boost)
    vector_boost: float = field(default_factory=lambda: settings.opensearch_vector_boost)

    def retrieve(
        self,
        workspace_id: str,
        query: str,
        k: int,
        *,
        query_vec: list[float] | None = None,
        database_url: str | None = None,
        embedding_version: str | None = None,
    ) -> list[RetrievedChunk]:
        import threading
        import time
        from app.providers.embeddings import embed

        # Embed once; share across both sub-retrievers.
        vec = query_vec or embed(query)
        ev = embedding_version or settings.embedding_version

        bm25_results: list[RetrievedChunk] = []
        vec_results: list[RetrievedChunk] = []
        errors: list[Exception] = []

        def _bm25() -> None:
            try:
                bm25_results.extend(
                    OpenSearchBM25Retriever().retrieve(
                        workspace_id, query, k * 2,
                        embedding_version=ev,
                    )
                )
            except Exception as e:
                errors.append(e)

        def _vector() -> None:
            try:
                vec_results.extend(
                    OpenSearchVectorRetriever().retrieve(
                        workspace_id, query, k * 2,
                        query_vec=vec,
                        embedding_version=ev,
                    )
                )
            except Exception as e:
                errors.append(e)

        t0 = time.time()
        t1 = threading.Thread(target=_bm25)
        t2 = threading.Thread(target=_vector)
        t1.start(); t2.start()
        t1.join(); t2.join()
        OS_HYBRID_LATENCY.observe(time.time() - t0)

        # Partial results are acceptable — degrade gracefully.
        return _rrf_fuse(
            bm25_results,
            vec_results,
            k=k,
            rrf_k=self.rrf_k,
            bm25_boost=self.bm25_boost,
            vector_boost=self.vector_boost,
        )
