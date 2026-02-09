from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Protocol, Sequence

from app.core.cache import cache
from app.core.config import settings
from app.core.observability import RETRIEVAL_LATENCY, persist_trace, timer
from app.indexing.index_state import get_index_state
from app.schemas import RetrievedChunk
from app.retrieval.slo import LatencyBudget
from app.retrieval.routing import choose_shards


class Retriever(Protocol):
    """Retriever interface.

    query_vec is optional so dense/hybrid retrievers can reuse a single query
    embedding computed once per request.

    database_url is optional to support logical sharding: the pipeline can fan
    out to multiple Postgres clusters and merge results.
    """

    def retrieve(
        self,
        workspace_id: str,
        query: str,
        k: int,
        *,
        query_vec: list[float] | None = None,
        database_url: str | None = None,
        embedding_version: str | None = None,
    ) -> list[RetrievedChunk]: ...


class Reranker(Protocol):
    def rerank(self, query: str, query_vec: list[float], docs: list[RetrievedChunk], k: int) -> list[RetrievedChunk]: ...


def _shards(workspace_id: str, query: str):
    return choose_shards(workspace_id, query)


def _hedged_retrieve(
    r: Retriever,
    *,
    workspace_id: str,
    query: str,
    k: int,
    query_vec: list[float],
    dsns: list[str | None],
    embedding_version: str,
) -> list[RetrievedChunk]:
    """Tail-latency mitigation via request hedging.

    If shard fanout is 1 but multiple shards exist, we issue a second request
    after a small delay and take the union. This is a simplified, dependency-
    free hedging strategy for p95/p99 protection.
    """

    if len(dsns) <= 1 or int(settings.shard_hedge_after_ms or 0) <= 0:
        return r.retrieve(workspace_id, query, k=k, query_vec=query_vec, database_url=dsns[0], embedding_version=embedding_version)

    primary = dsns[0]
    hedge = dsns[1]
    delay_s = max(0.0, float(settings.shard_hedge_after_ms) / 1000.0)

    out: list[RetrievedChunk] = []
    lock = threading.Lock()

    def _call(dsn: str | None, *, delay: float) -> None:
        if delay:
            time.sleep(delay)
        res = r.retrieve(workspace_id, query, k=k, query_vec=query_vec, database_url=dsn, embedding_version=embedding_version)
        with lock:
            out.extend(res)

    t1 = threading.Thread(target=_call, kwargs={"dsn": primary, "delay": 0.0})
    t2 = threading.Thread(target=_call, kwargs={"dsn": hedge, "delay": delay_s})
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    return out


def _cache_key(parts: Sequence[str]) -> str:
    raw = "|".join(parts)
    h = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:32]
    return f"retrieval:{h}"


@dataclass
class RetrievalPipeline:
    retrievers: list[Retriever]
    fusion_method: str = "rrf"
    rrf_k: int = 60
    reranker: Reranker | None = None
    experiment: str = "baseline"

    def run(
        self,
        workspace_id: str,
        query: str,
        *,
        query_vec: list[float],
        k: int,
        rerank_candidates: int,
        embedding_version_override: str | None = None,
    ) -> tuple[list[RetrievedChunk], int]:
        # Cache retrieval results (not generation) to improve p95 and reduce DB load.
        # Workspace-scoped active embedding version enables safe, zero-downtime reindexing.
        idx_state = get_index_state(workspace_id)
        active_embedding_version = idx_state.active_embedding_version
        embedding_version = embedding_version_override or active_embedding_version
        index_epoch = idx_state.index_epoch

        # Key includes embedding_version + experiment so rollouts are isolated.
        # It also includes index_epoch to prevent stale cache reads after
        # ingestion, deletes, or reindex/migration events.
        key = _cache_key([
            workspace_id,
            self.experiment,
            embedding_version,
            str(index_epoch),
            str(k),
            str(rerank_candidates),
            query.strip().lower(),
        ])
        cached = cache.get_json(key)
        if cached is not None:
            hits = [RetrievedChunk(**d) for d in cached.get("hits", [])]
            persist_trace(
                trace_type="retrieval",
                workspace_id=workspace_id,
                body={
                    "cached": True,
                    "cache_key": key,
                    "experiment": self.experiment,
                    "embedding_version": embedding_version,
                    "hits": [d.model_dump() for d in hits],
                },
                latency_ms=int(cached.get("latency_ms", 0)),
            )
            return hits[:k], int(cached.get("latency_ms", 0))

        with timer(RETRIEVAL_LATENCY):
            t0 = time.time()

            stage_results: list[list[RetrievedChunk]] = []
            routed = _shards(workspace_id, query)
            shard_dsns = routed.dsns
            if routed.consistency_error:
                persist_trace(
                    trace_type="retrieval",
                    workspace_id=workspace_id,
                    body={
                        "cached": False,
                        "experiment": self.experiment,
                    "embedding_version": embedding_version,
                        "consistency": "strict",
                        "error": routed.consistency_error,
                        "epochs": routed.epochs,
                        "index_epoch": index_epoch,
                    },
                    latency_ms=0,
                )
                return [], 0

            budget = LatencyBudget.start(settings.retrieval_budget_ms)

            # Fan-out to shards and merge per stage.
            for r in self.retrievers:
                if budget.expired():
                    break
                merged: list[RetrievedChunk] = []
                # If we only query a single shard (fanout==1) but have multiple
                # shards available, hedge to protect tail latency.
                if len(shard_dsns) >= 2 and int(settings.retrieval_shard_fanout or 0) == 1:
                    merged.extend(
                        _hedged_retrieve(
                            r,
                            workspace_id=workspace_id,
                            query=query,
                            k=rerank_candidates,
                            query_vec=query_vec,
                            dsns=shard_dsns,
                            embedding_version=embedding_version,
                        )
                    )
                else:
                    for dsn in shard_dsns:
                        if budget.expired():
                            break
                        merged.extend(r.retrieve(workspace_id, query, k=rerank_candidates, query_vec=query_vec, database_url=dsn, embedding_version=embedding_version))
                # Keep best per id (dedupe across shards)
                by_id: dict[str, RetrievedChunk] = {}
                for doc in merged:
                    prev = by_id.get(doc.id)
                    if prev is None or doc.score > prev.score:
                        by_id[doc.id] = doc
                stage_results.append(sorted(by_id.values(), key=lambda x: x.score, reverse=True)[:rerank_candidates])

            fused = self._fuse(stage_results, top_k=rerank_candidates)

            out = fused
            if self.reranker and budget.allow(settings.reranker_timeout_ms):
                out = self.reranker.rerank(query, query_vec, fused, k=k)
            else:
                out = out[:k]

            latency_ms = int((time.time() - t0) * 1000)
            cache.set_json(
                key,
                {
                    "hits": [d.model_dump() for d in out],
                    "latency_ms": latency_ms,
                },
            )

            persist_trace(
                trace_type="retrieval",
                workspace_id=workspace_id,
                body={
                    "cached": False,
                    "experiment": self.experiment,
                    "embedding_version": embedding_version,
                    "fusion": self.fusion_method,
                    "rrf_k": self.rrf_k,
                    "index_state": {"active_embedding_version": active_embedding_version, "index_epoch": index_epoch},
                    "routing": {
                        "strategy": settings.retrieval_routing_strategy,
                        "fanout": settings.retrieval_shard_fanout,
                    },
                    "shards": [s for s in shard_dsns if s],
                    "shard_epochs": routed.epochs,
                    "budget_ms": settings.retrieval_budget_ms,
                    "stages": [len(x) for x in stage_results],
                    "hits": [d.model_dump() for d in out],
                },
                latency_ms=latency_ms,
            )
            return out, latency_ms

    def _fuse(self, results: list[list[RetrievedChunk]], *, top_k: int) -> list[RetrievedChunk]:
        if not results:
            return []
        if self.fusion_method == "concat":
            seen = set()
            out: list[RetrievedChunk] = []
            for stage in results:
                for d in stage:
                    if d.id in seen:
                        continue
                    seen.add(d.id)
                    out.append(d)
                    if len(out) >= top_k:
                        return out
            return out

        # Reciprocal Rank Fusion
        scores: dict[str, float] = {}
        by_id: dict[str, RetrievedChunk] = {}
        for stage in results:
            for rank, d in enumerate(stage, start=1):
                scores[d.id] = scores.get(d.id, 0.0) + 1.0 / (self.rrf_k + rank)
                if d.id not in by_id:
                    by_id[d.id] = d

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        out: list[RetrievedChunk] = []
        for cid, s in ranked[:top_k]:
            d = by_id[cid]
            d.score = float(s)
            out.append(d)
        return out
