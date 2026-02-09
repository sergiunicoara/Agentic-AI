from __future__ import annotations

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
    # very small, dependency-free cache suitable for single-process dev and CI.
    # In production you'd use Redis or an in-process LRU.
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
    """Fetch candidate embeddings efficiently.

    Improvements vs the naive approach:
    - Reuses an in-process cache across requests/eval runs.
    - Fetches missing embeddings in a single batch query.
    - Avoids parsing vector->text by casting to a Postgres array.
    """
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

    if not missing:
        return out

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


class MMRReranker:
    """Maximum Marginal Relevance reranking.

    This demonstrates multi-stage retrieval: cheap candidate generation + expensive reranking.
    """

    def __init__(self, lambda_: float = 0.75):
        self.lambda_ = float(lambda_)

    def rerank(self, query: str, query_vec: list[float], docs: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
        if not docs:
            return []
        cand = docs[:]
        k = min(int(k), len(cand))
        ids = [d.id for d in cand]
        ev = str((cand[0].meta or {}).get("embedding_version") or settings.embedding_version)
        embs = _fetch_embeddings(ids, embedding_version=ev)

        selected: list[RetrievedChunk] = []
        selected_ids: set[str] = set()

        while len(selected) < k:
            best = None
            best_score = -1e9
            for d in cand:
                if d.id in selected_ids:
                    continue
                e = embs.get(d.id)
                rel = _cosine(query_vec, e) if e else float(d.score)
                div = 0.0
                if selected and e:
                    div = max(_cosine(e, embs.get(s.id, [])) for s in selected)
                mmr = (self.lambda_ * rel) - ((1.0 - self.lambda_) * div)
                if mmr > best_score:
                    best_score = mmr
                    best = d

            if best is None:
                break
            best.meta = {**best.meta, "mmr": float(best_score)}
            selected.append(best)
            selected_ids.add(best.id)

        return selected
