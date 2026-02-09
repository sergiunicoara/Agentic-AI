from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml

from app.core.config import settings
from app.retrieval.pipeline import RetrievalPipeline
from app.retrieval.retrievers.dense import DenseRetriever
from app.retrieval.retrievers.lexical import LexicalRetriever
from app.retrieval.rerankers.mmr import MMRReranker
from app.retrieval.rerankers.cross_encoder_stub import CrossEncoderStubReranker


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
    if mode == "dense":
        retrievers = [DenseRetriever()]
    elif mode == "lexical":
        retrievers = [LexicalRetriever()]
    else:
        retrievers = [DenseRetriever(), LexicalRetriever()]

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
