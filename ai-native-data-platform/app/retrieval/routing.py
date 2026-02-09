from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from app.core.config import settings
from app.retrieval.consistency import fetch_shard_epochs, consistent_epochs


def _stable_hash(s: str) -> int:
    h = hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()
    return int(h[:16], 16)


def _rendezvous_score(key: str, node: str) -> int:
    # Highest Random Weight hashing (rendezvous).
    return _stable_hash(f"{key}|{node}")


@dataclass(frozen=True)
class RoutedShards:
    dsns: list[str | None]
    epochs: list[dict] | None = None
    consistency_error: str | None = None


def parse_shards() -> list[str | None]:
    if not settings.retrieval_shard_dsns.strip():
        return [None]
    dsns = [d.strip() for d in settings.retrieval_shard_dsns.split(",") if d.strip()]
    return dsns or [None]


def choose_shards(workspace_id: str, query: str) -> RoutedShards:
    """Select which shards to query.

    Strategies:
    - fanout: query every shard (baseline)
    - rendezvous: pick a deterministic subset using HRW hashing
    - adaptive: like rendezvous, but can reshuffle for load/health (simplified)

    Consistency:
    - strict mode checks shard epochs before serving.
    """

    all_shards = parse_shards()
    if len(all_shards) == 1:
        return RoutedShards(dsns=all_shards)

    strategy = (settings.retrieval_routing_strategy or "fanout").lower()
    fanout = int(settings.retrieval_shard_fanout or 0)

    selected: list[str | None]
    if strategy == "fanout" or fanout <= 0:
        selected = all_shards
    else:
        key = f"{workspace_id}|{query.strip().lower()}"
        ranked = sorted(all_shards, key=lambda d: _rendezvous_score(key, str(d)), reverse=True)
        selected = ranked[: max(1, min(fanout, len(ranked)))]

        if strategy == "adaptive":
            # Placeholder for health-aware routing. To keep this repo self-contained
            # (and DB-independent in unit tests), we apply a tiny stochastic
            # shuffle for tail avoidance.
            if len(selected) > 1 and random.random() < 0.05:
                random.shuffle(selected)

    # Strict cross-shard epoch check (optional)
    epochs_out: list[dict] | None = None
    consistency_error: str | None = None
    if settings.shard_consistency_mode.lower() == "strict":
        dsns = [s for s in selected if s]
        if len(dsns) > 1:
            epochs = fetch_shard_epochs(dsns)
            epochs_out = [{"dsn": e.dsn, "index_epoch": e.index_epoch} for e in epochs]
            if not consistent_epochs(epochs):
                consistency_error = "cross_shard_epoch_mismatch"

    return RoutedShards(dsns=selected, epochs=epochs_out, consistency_error=consistency_error)
