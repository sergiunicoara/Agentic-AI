from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml

from app.core.config import settings
from app.retrieval.pipeline import RetrievalPipeline
from app.retrieval.retrievers.dense import DenseRetriever
from app.retrieval.retrievers.lexical import LexicalRetriever
from app.retrieval.retrievers.multimodal import MultimodalDenseRetriever
from app.retrieval.rerankers.mmr import MMRReranker
from app.retrieval.rerankers.cross_encoder_stub import CrossEncoderStubReranker

# OpenSearch retrievers — imported lazily so the app starts without opensearch-py
def _os_bm25():
    from app.retrieval.retrievers.opensearch_retriever import OpenSearchBM25Retriever
    return OpenSearchBM25Retriever()

def _os_vector():
    from app.retrieval.retrievers.opensearch_retriever import OpenSearchVectorRetriever
    return OpenSearchVectorRetriever()

def _os_hybrid():
    from app.retrieval.retrievers.opensearch_retriever import OpenSearchHybridRetriever
    return OpenSearchHybridRetriever()


def _load_experiment_config(experiment: str) -> dict[str, Any]:
    # Accept explicit file path, otherwise look in app/eval/experiments.
    path = experiment
    if not (os.path.isfile(path) and path.endswith((".yml", ".yaml"))):
        path = os.path.join("app", "eval", "experiments", f"{experiment}.yaml")
    if not os.path.isfile(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _pick(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


@lru_cache(maxsize=32)
def build_pipeline(experiment: str | None = None) -> RetrievalPipeline:
    """Build a retrieval pipeline.

    If an experiment is provided and a matching YAML config exists, the pipeline
    is parameterized from the experiment's `retrieval` section.
    """

    exp_name = (experiment or settings.ab_default_experiment or "baseline").strip()
    cfg = _load_experiment_config(exp_name)

    mode = str(_pick(cfg, "retrieval", "mode", default=settings.retrieval_mode) or "dense").lower()
    fusion = str(_pick(cfg, "retrieval", "fusion", default=settings.fusion_method) or "rrf").lower()
    rrf_k = int(_pick(cfg, "retrieval", "rrf_k", default=settings.rrf_k) or settings.rrf_k)

    rerank_mode = str(_pick(cfg, "retrieval", "rerank", default=settings.rerank_mode) or "none").lower()
    mmr_lambda = float(_pick(cfg, "retrieval", "mmr_lambda", default=settings.mmr_lambda) or settings.mmr_lambda)
    cross_alpha = float(
        _pick(cfg, "retrieval", "cross_alpha", default=settings.cross_rerank_alpha) or settings.cross_rerank_alpha
    )

    retrievers = []
    if mode == "multimodal":
        retrievers = [MultimodalDenseRetriever()]
    elif mode == "dense":
        retrievers = [DenseRetriever()]
    elif mode == "lexical":
        retrievers = [LexicalRetriever()]
    # ── OpenSearch backends ─────────────────────────────────────────────────
    elif mode == "opensearch_bm25":
        retrievers = [_os_bm25()]
    elif mode == "opensearch_vector":
        retrievers = [_os_vector()]
    elif mode == "opensearch_hybrid":
        # Single retriever handles internal BM25+vector+RRF; pipeline fusion is concat.
        retrievers = [_os_hybrid()]
        fusion = "concat"   # RRF already applied inside the retriever
    elif mode == "opensearch_hybrid_rerank":
        # Expose BM25 and vector as separate stages so the pipeline's RRF runs on top,
        # then optionally reranks. Gives the outer pipeline full control over fusion.
        retrievers = [_os_bm25(), _os_vector()]
    # ───────────────────────────────────────────────────────────────────────
    else:
        # hybrid: use multimodal dense when MULTIMODAL_RETRIEVAL=true, else standard dense.
        dense = MultimodalDenseRetriever() if settings.multimodal_retrieval else DenseRetriever()
        retrievers = [dense, LexicalRetriever()]

    reranker = None
    if rerank_mode == "mmr":
        reranker = MMRReranker(lambda_=mmr_lambda)
    elif rerank_mode == "cross":
        reranker = CrossEncoderStubReranker(alpha=cross_alpha)

    return RetrievalPipeline(
        retrievers=retrievers,
        fusion_method=fusion,
        rrf_k=rrf_k,
        reranker=reranker,
        experiment=exp_name,
    )
