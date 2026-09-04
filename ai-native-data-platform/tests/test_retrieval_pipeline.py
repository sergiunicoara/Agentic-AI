"""Regression tests for two bugs fixed in the retrieval cache layer:

1. A cache hit must report latency_ms == 0, never the latency the original
   (uncached) computation took — a nonzero stored value previously tripped
   the online enforce_latency() contract and degraded a valid answer to
   "unknown" purely because it came from cache.
2. The cache key must change whenever index_epoch changes, so a post-
   ingestion cache invalidation (bump_index_epoch) actually bypasses stale
   Redis entries instead of continuing to hit them.
"""
from __future__ import annotations

from app.indexing.index_state import WorkspaceIndexState
from app.retrieval.pipeline import RetrievalPipeline, _cache_key
from app.schemas import RetrievedChunk


class TestCacheKeyIncludesIndexEpoch:

    def test_different_epoch_produces_different_key(self):
        base_parts = ["ws1", "baseline", "v1", "5", "8", "some query"]
        key_epoch_0 = _cache_key(["ws1", "baseline", "v1", "0", "8", "25", "some query"])
        key_epoch_1 = _cache_key(["ws1", "baseline", "v1", "1", "8", "25", "some query"])
        assert key_epoch_0 != key_epoch_1

    def test_same_inputs_produce_same_key(self):
        parts = ["ws1", "baseline", "v1", "3", "8", "25", "some query"]
        assert _cache_key(parts) == _cache_key(list(parts))


class TestCacheHitLatency:

    def test_cache_hit_returns_zero_latency_even_when_stored_value_is_nonzero(self, monkeypatch):
        import app.retrieval.pipeline as pipeline_mod

        stored_chunk = RetrievedChunk(
            id="c1", document_id="d1", chunk_index=0, text="cached text", score=0.9,
        )
        cached_payload = {
            "hits": [stored_chunk.model_dump()],
            # This is the value that used to leak straight into the response,
            # exceeding the 800ms online contract and forcing an "unknown"
            # answer for a request that was actually served instantly.
            "latency_ms": 875,
        }
        monkeypatch.setattr(pipeline_mod.cache, "get_json", lambda key: cached_payload)
        monkeypatch.setattr(
            pipeline_mod,
            "get_index_state",
            lambda workspace_id: WorkspaceIndexState(
                workspace_id=workspace_id,
                active_embedding_version="v1",
                target_embedding_version=None,
                index_epoch=3,
                updated_at_s=0.0,
            ),
        )

        pipeline = RetrievalPipeline(retrievers=[])
        hits, latency_ms = pipeline.run(
            "ws1",
            "some query",
            query_vec=[0.1, 0.2],
            k=5,
            rerank_candidates=25,
        )

        assert latency_ms == 0
        assert len(hits) == 1
        assert hits[0].id == "c1"

    def test_cache_hit_respects_k_even_with_more_cached_hits(self, monkeypatch):
        import app.retrieval.pipeline as pipeline_mod

        chunks = [
            RetrievedChunk(id=f"c{i}", document_id="d1", chunk_index=i, text=f"t{i}", score=1.0 - i * 0.1)
            for i in range(5)
        ]
        cached_payload = {"hits": [c.model_dump() for c in chunks], "latency_ms": 42}
        monkeypatch.setattr(pipeline_mod.cache, "get_json", lambda key: cached_payload)
        monkeypatch.setattr(
            pipeline_mod,
            "get_index_state",
            lambda workspace_id: WorkspaceIndexState(
                workspace_id=workspace_id,
                active_embedding_version="v1",
                target_embedding_version=None,
                index_epoch=0,
                updated_at_s=0.0,
            ),
        )

        pipeline = RetrievalPipeline(retrievers=[])
        hits, latency_ms = pipeline.run(
            "ws1", "q", query_vec=[0.1], k=2, rerank_candidates=25,
        )

        assert latency_ms == 0
        assert len(hits) == 2
