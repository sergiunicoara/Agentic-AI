from __future__ import annotations

"""A lightweight "cross-encoder-like" reranker.

Real RAG platforms typically use an expensive semantic reranker
(cross-encoder, ColBERT-style late interaction, or an LLM ranker) on a bounded
set of candidates.

This scaffold intentionally avoids heavyweight model dependencies. Instead, we
approximate a cross-encoder by combining:
  - embedding cosine similarity (semantic)
  - token overlap score (lexical precision)

It is deterministic, cheap, and good enough to demonstrate multi-stage
retrieval and evaluation wiring.
"""

import math

from sqlalchemy import text

from app.core.config import settings
from app.data.db import read_session_scope
from app.schemas import RetrievedChunk


_EMB_CACHE: dict[tuple[str, str], list[float]] = {}
_EMB_CACHE_MAX = 5000


def _cache_get(embedding_version: str, chunk_id: str) -> list[float] | None:
    return _EMB_CACHE.get((embedding_version, chunk_id))


def _cache_set(embedding_version: str, chunk_id: str, vec: list[float]) -> None:
    if len(_EMB_CACHE) >= _EMB_CACHE_MAX:
        _EMB_CACHE.pop(next(iter(_EMB_CACHE)))
    _EMB_CACHE[(embedding_version, chunk_id)] = vec


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / math.sqrt(na * nb)


def _fetch_embeddings(chunk_ids: list[str], *, embedding_version: str) -> dict[str, list[float]]:
    if not chunk_ids:
        return {}

    out: dict[str, list[float]] = {}
    missing: list[str] = []
    for cid in chunk_ids:
        v = _cache_get(embedding_version, cid)
        if v is None:
            missing.append(cid)
        else:
            out[cid] = v

    if missing:
        sql = text(
            """
            SELECT id::text AS chunk_id, (embedding::real[]) AS emb
            FROM document_chunk
            WHERE id = ANY(:ids)
              AND embedding_version = :embedding_version
            """
        )
        with read_session_scope() as db:
            rows = db.execute(sql, {"ids": missing, "embedding_version": embedding_version}).mappings().all()

        for r in rows:
            vec = [float(x) for x in (r["emb"] or [])]
            out[r["chunk_id"]] = vec
            _cache_set(embedding_version, r["chunk_id"], vec)

    return out


def _token_overlap(query: str, text_: str) -> float:
    q = [t for t in (query or "").lower().split() if t]
    if not q:
        return 0.0
    doc = set([t for t in (text_ or "").lower().split() if t])
    hit = sum(1 for t in q if t in doc)
    return float(hit) / float(len(q))


class CrossEncoderStubReranker:
    def __init__(self, *, alpha: float = 0.7):
        # alpha weights semantic cosine; (1-alpha) weights lexical overlap
        self.alpha = max(0.0, min(1.0, float(alpha)))

    def rerank(self, query: str, query_vec: list[float], docs: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
        if not docs:
            return []
        cand = docs[:]
        ids = [d.id for d in cand]
        ev = str((cand[0].meta or {}).get("embedding_version") or settings.embedding_version)
        embs = _fetch_embeddings(ids, embedding_version=ev)

        scored: list[tuple[float, RetrievedChunk]] = []
        for d in cand:
            e = embs.get(d.id)
            sem = _cosine(query_vec, e) if e else float(d.score)
            lex = _token_overlap(query, d.text)
            s = (self.alpha * sem) + ((1.0 - self.alpha) * lex)
            d.meta = {**d.meta, "rerank_sem": float(sem), "rerank_lex": float(lex)}
            scored.append((float(s), d))

        scored.sort(key=lambda x: x[0], reverse=True)
        out = [d for _s, d in scored[: max(1, int(k))]]
        for d, (_s, _d) in zip(out, scored[: len(out)]):
            d.score = float(_s)
        return out
