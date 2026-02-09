from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import text

from app.core.config import settings
from app.data.db import write_session_scope


@dataclass(frozen=True)
class PgvectorScalingPlan:
    partitions: int
    index_type: str  # ivfflat | hnsw
    lists: int | None = None
    m: int | None = None
    ef_construction: int | None = None


def recommend_plan(*, estimated_rows: int) -> PgvectorScalingPlan:
    """Return a conservative default scaling plan.

    Heuristics:
    - Use partitions to keep each partition under ~25M rows.
    - HNSW is generally better for online workloads; IVF can be cheaper for bulk.
    """
    partitions = max(1, int(math.ceil(max(1, estimated_rows) / 25_000_000)))
    # Default to HNSW once you're big enough to care.
    if estimated_rows >= 2_000_000:
        return PgvectorScalingPlan(partitions=partitions, index_type="hnsw", m=16, ef_construction=64)
    lists = max(100, int(math.sqrt(max(1, estimated_rows))))
    return PgvectorScalingPlan(partitions=partitions, index_type="ivfflat", lists=lists)


def ensure_partitions(*, partitions: int, table: str = "document_chunk", key: str = "workspace_id") -> None:
    """Create hash partitions for the vector table.

    This assumes Postgres declarative partitioning and a schema where the table
    can be recreated. In real deployments you'd do this during a maintenance
    window or via online table migration.
    """
    parts = int(partitions)
    if parts < 1:
        raise ValueError("partitions must be >= 1")

    # Idempotent: only creates partitions if they do not exist.
    with write_session_scope() as db:
        db.execute(text("SET LOCAL statement_timeout = 0"))
        for i in range(parts):
            db.execute(
                text(
                    f"""
                    DO $$
                    BEGIN
                      IF NOT EXISTS (
                        SELECT 1 FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relname = '{table}_p{i}' AND n.nspname = 'public'
                      ) THEN
                        EXECUTE 'CREATE TABLE {table}_p{i} PARTITION OF {table} FOR VALUES WITH (MODULUS {parts}, REMAINDER {i})';
                      END IF;
                    END $$;
                    """
                )
            )


def ensure_vector_indexes(
    *,
    index_type: str,
    table: str = "document_chunk",
    embedding_col: str = "embedding",
    opclass: str = "vector_cosine_ops",
    lists: int | None = None,
    m: int | None = None,
    ef_construction: int | None = None,
) -> None:
    """Create vector indexes suitable for scaling.

    - IVF: good throughput, requires ANALYZE and reasonable `lists`.
    - HNSW: better recall/latency tradeoff; higher build cost.

    We create indexes CONCURRENTLY to reduce downtime.
    """
    it = index_type.lower()
    with write_session_scope() as db:
        db.execute(text("SET LOCAL statement_timeout = 0"))

        if it == "ivfflat":
            if lists is None:
                raise ValueError("lists is required for ivfflat")
            db.execute(
                text(
                    f"""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS {table}_{embedding_col}_ivf
                    ON {table} USING ivfflat ({embedding_col} {opclass})
                    WITH (lists = :lists)
                    """
                ),
                {"lists": int(lists)},
            )
        elif it == "hnsw":
            if m is None or ef_construction is None:
                raise ValueError("m and ef_construction are required for hnsw")
            db.execute(
                text(
                    f"""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS {table}_{embedding_col}_hnsw
                    ON {table} USING hnsw ({embedding_col} {opclass})
                    WITH (m = :m, ef_construction = :ef)
                    """
                ),
                {"m": int(m), "ef": int(ef_construction)},
            )
        else:
            raise ValueError("index_type must be ivfflat or hnsw")


def analyze_table(*, table: str = "document_chunk") -> None:
    with write_session_scope() as db:
        db.execute(text("ANALYZE " + table))
