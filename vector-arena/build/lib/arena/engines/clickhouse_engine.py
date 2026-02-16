import os
import numpy as np
from .base import EngineResult

class ClickHouseEngine:
    """
    ClickHouse vector search wrapper.
    Requires env vars:
      - CLICKHOUSE_HOST (default localhost)
      - CLICKHOUSE_PORT (default 9000)
      - CLICKHOUSE_USER (default default)
      - CLICKHOUSE_PASSWORD (default empty)
      - CLICKHOUSE_DB (default default)
    NOTE: ClickHouse vector support and query syntax depend on version and table engine.
    This implementation is a minimal template and may require adjustments.
    """
    name = "clickhouse"

    def __init__(self, dim: int):
        self.dim = dim
        self.host = os.getenv("CLICKHOUSE_HOST","localhost")
        self.port = int(os.getenv("CLICKHOUSE_PORT","9000"))
        self.user = os.getenv("CLICKHOUSE_USER","default")
        self.password = os.getenv("CLICKHOUSE_PASSWORD","")
        self.db = os.getenv("CLICKHOUSE_DB","default")
        self._client = None

    def build(self, docs: np.ndarray) -> None:
        try:
            from clickhouse_driver import Client
        except Exception as e:
            raise ImportError("clickhouse-driver not installed. Install with: pip install clickhouse-driver") from e

        self._client = Client(host=self.host, port=self.port, user=self.user, password=self.password, database=self.db)
        self._client.execute("DROP TABLE IF EXISTS docs")
        # Basic table. For ANN you'd use experimental/vector index features depending on CH version.
        self._client.execute("CREATE TABLE docs (id UInt32, vector Array(Float32)) ENGINE = MergeTree ORDER BY id")
        docs = np.asarray(docs, dtype=np.float32)
        data=[(int(i), v.tolist()) for i,v in enumerate(docs)]
        self._client.execute("INSERT INTO docs VALUES", data)

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        if self._client is None:
            raise RuntimeError("Client not initialized. Did build() run?")
        queries = np.asarray(queries, dtype=np.float32)
        ids = np.full((queries.shape[0], k), -1, dtype=np.int64)
        for i,q in enumerate(queries):
            # Brute-force cosine via dot product on normalized vectors (slow). Replace with native ANN when available.
            res = self._client.execute(
                "SELECT id FROM docs ORDER BY arraySum(arrayMap((a,b)->a*b, vector, %(q)s)) DESC LIMIT %(k)s",
                {"q": q.tolist(), "k": int(k)}
            )
            row=[int(r[0]) for r in res]
            row = row[:k] + [-1]*(k-len(row))
            ids[i]=np.array(row,dtype=np.int64)
        return EngineResult(ids=ids)
