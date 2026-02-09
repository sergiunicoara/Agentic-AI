from __future__ import annotations

"""Cross-shard consistency signals.

In distributed retrieval deployments, shards (or read replicas) can be at
different freshness levels. A platform typically exposes a **consistency mode**
so callers can choose between...
"""

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text

from app.data.db import session_scope


@dataclass(frozen=True)
class ShardConsistency:
    dsn: str
    index_epoch: str | None


def fetch_shard_epochs(shard_dsns: Iterable[str]) -> list[ShardConsistency]:
    out: list[ShardConsistency] = []
    for dsn in shard_dsns:
        try:
            with session_scope(dsn) as db:
                row = db.execute(text("SELECT index_epoch::text FROM shard_state LIMIT 1")).fetchone()
            out.append(ShardConsistency(dsn=dsn, index_epoch=row[0] if row else None))
        except Exception:
            out.append(ShardConsistency(dsn=dsn, index_epoch=None))
    return out


def consistent_epochs(epochs: list[ShardConsistency]) -> bool:
    vals = [e.index_epoch for e in epochs if e.index_epoch]
    if not vals:
        return True  # unknown -> best effort
    return len(set(vals)) == 1
