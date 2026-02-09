import os

import pytest

from app.generation.service import run_rag_safe
from app.schemas import RetrievedChunk


def test_generation_safe_degradation_on_provider_failure(monkeypatch):
    # Force LLM provider to fail
    def boom(prompt: str) -> str:
        raise RuntimeError("provider_down")

    monkeypatch.setattr("app.providers.llm.generate", boom)

    hits = [RetrievedChunk(id="c1", document_id="d1", chunk_index=0, text="ctx", score=0.9, meta={})]
    out, ms, err = run_rag_safe("demo", "q", hits)
    assert out.unknown is True
    assert "don’t know" in out.answer.lower()
    assert err is not None


def test_retrieval_cache_does_not_throw(monkeypatch):
    # Ensure cache failures behave like misses
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # invalid
    from app.core.cache import Cache
    c = Cache()
    assert c.get_json("k") is None
