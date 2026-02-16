import os
from typing import List

import numpy as np

from .base import EngineResult


class PgVectorEngine:
    """PostgreSQL + pgvector.

    Uses cosine distance (<=>) on a vector column.
    """

    name = "pgvector"

    def __init__(self, dim: int):
        try:
            import psycopg  # type: ignore
        except Exception as e:
            raise ImportError("psycopg not installed. Install with: pip install psycopg[binary]") from e

        self._psycopg = psycopg
        self.dim = dim

        # Prefer a single DSN env; fall back to composed settings.
        dsn = os.getenv("PGVECTOR_DSN")
        if not dsn:
            host = os.getenv("PGVECTOR_HOST", "localhost")
            port = int(os.getenv("PGVECTOR_PORT", "5432"))
            user = os.getenv("PGVECTOR_USER", "postgres")
            password = os.getenv("PGVECTOR_PASSWORD", "postgres")
            db = os.getenv("PGVECTOR_DB", "postgres")
            dsn = f"postgresql://{user}:{password}@{host}:{port}/{db}"

        self.table = os.getenv("PGVECTOR_TABLE", "vector_arena_docs")
        self._conn = psycopg.connect(dsn, autocommit=True)

        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(f"DROP TABLE IF EXISTS {self.table}")
            cur.execute(f"CREATE TABLE {self.table} (id INT PRIMARY KEY, v vector({int(dim)}))")

    @staticmethod
    def _vec_literal(x: np.ndarray) -> str:
        # pgvector accepts '[1,2,3]' literal
        arr = np.asarray(x, dtype=np.float32)
        return "[" + ",".join(f"{float(v):.8f}" for v in arr.tolist()) + "]"

    def build(self, docs: np.ndarray) -> None:
        batch = int(os.getenv("UPSERT_BATCH", "512"))
        with self._conn.cursor() as cur:
            for s in range(0, docs.shape[0], batch):
                e = min(s + batch, docs.shape[0])
                rows = [(int(i), self._vec_literal(docs[i])) for i in range(s, e)]
                cur.executemany(
                    f"INSERT INTO {self.table} (id, v) VALUES (%s, %s::vector)",
                    rows,
                )

            # Index (optional). HNSW is supported by pgvector >=0.5.0; IVFFlat is widely available.
            index_kind = os.getenv("PGVECTOR_INDEX", "ivfflat").lower().strip()
            if index_kind == "none":
                return

            if index_kind == "hnsw":
                m = int(os.getenv("PGVECTOR_HNSW_M", "16"))
                efc = int(os.getenv("PGVECTOR_HNSW_EF_CONSTRUCTION", "128"))
                cur.execute(
                    f"CREATE INDEX {self.table}_v_hnsw ON {self.table} USING hnsw (v vector_cosine_ops) WITH (m={m}, ef_construction={efc})"
                )
            else:
                lists = int(os.getenv("PGVECTOR_IVFFLAT_LISTS", "100"))
                cur.execute(
                    f"CREATE INDEX {self.table}_v_ivfflat ON {self.table} USING ivfflat (v vector_cosine_ops) WITH (lists={lists})"
                )

            # Collect stats to help planner
            cur.execute(f"ANALYZE {self.table}")

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        out = np.empty((queries.shape[0], k), dtype=np.int64)
        # Tune IVFFlat probes / HNSW ef_search
        probes = os.getenv("PGVECTOR_PROBES")
        ef_search = os.getenv("PGVECTOR_EF_SEARCH")

        with self._conn.cursor() as cur:
            if probes:
                cur.execute(f"SET ivfflat.probes = {int(probes)}")
            if ef_search:
                cur.execute(f"SET hnsw.ef_search = {int(ef_search)}")

            for i in range(queries.shape[0]):
                vec = self._vec_literal(queries[i])
                cur.execute(
                    f"SELECT id FROM {self.table} ORDER BY v <=> %s::vector LIMIT %s",
                    (vec, int(k)),
                )
                rows = cur.fetchall() or []
                ids: List[int] = [int(r[0]) for r in rows]
                if len(ids) < k:
                    ids += [-1] * (k - len(ids))
                out[i] = np.array(ids[:k], dtype=np.int64)

        return EngineResult(ids=out)
