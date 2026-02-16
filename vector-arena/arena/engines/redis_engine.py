import os
import time
from typing import List

import numpy as np

from .base import EngineResult


class RedisEngine:
    """Redis Vector Search via RediSearch (redis-stack).

    Requires a Redis instance with RediSearch enabled (e.g. redis/redis-stack-server).
    """

    name = "redis"

    def __init__(self, dim: int):
        try:
            import redis  # type: ignore
        except Exception as e:
            raise ImportError("redis not installed. Install with: pip install redis") from e

        self.dim = dim
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD")
        self.index = os.getenv("REDIS_INDEX", "vector_arena")
        self.prefix = os.getenv("REDIS_PREFIX", "doc:")

        self._r = redis.Redis(host=host, port=port, password=password, decode_responses=False)

        # Best-effort cleanup
        try:
            self._r.execute_command("FT.DROPINDEX", self.index, "DD")
        except Exception:
            pass

        # Create HNSW vector index
        m = int(os.getenv("REDIS_HNSW_M", "16"))
        efc = int(os.getenv("REDIS_HNSW_EF_CONSTRUCTION", "128"))
        try:
            self._r.execute_command(
                "FT.CREATE",
                self.index,
                "ON",
                "HASH",
                "PREFIX",
                "1",
                self.prefix,
                "SCHEMA",
                "v",
                "VECTOR",
                "HNSW",
                # IMPORTANT: this number is the count of algorithm parameters that follow.
                # We provide 5 key/value pairs => 10 tokens.
                "10",
                "TYPE",
                "FLOAT32",
                "DIM",
                str(dim),
                "DISTANCE_METRIC",
                "COSINE",
                "M",
                str(m),
                "EF_CONSTRUCTION",
                str(efc),
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create RediSearch index '{self.index}': {e}")

    @staticmethod
    def _vec_bytes(x: np.ndarray) -> bytes:
        return np.asarray(x, dtype=np.float32).tobytes(order="C")

    def build(self, docs: np.ndarray) -> None:
        batch = int(os.getenv("UPSERT_BATCH", "512"))
        pipe = self._r.pipeline(transaction=False)
        for s in range(0, docs.shape[0], batch):
            e = min(s + batch, docs.shape[0])
            for i in range(s, e):
                key = f"{self.prefix}{int(i)}".encode("utf-8")
                pipe.hset(key, mapping={b"v": self._vec_bytes(docs[i])})
            pipe.execute()

        # Optional short pause for indexing
        time.sleep(float(os.getenv("REDIS_POST_BUILD_SLEEP_SEC", "0")))

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        out = np.empty((queries.shape[0], k), dtype=np.int64)
        dialect = int(os.getenv("REDIS_DIALECT", "2"))

        for i in range(queries.shape[0]):
            q = "*=>[KNN {} @v $vec AS score]".format(int(k))
            res = self._r.execute_command(
                "FT.SEARCH",
                self.index,
                q,
                "PARAMS",
                "2",
                "vec",
                self._vec_bytes(queries[i]),
                "SORTBY",
                "score",
                "RETURN",
                "0",
                "DIALECT",
                str(dialect),
            )

            # Format: [total, key1, [..fields..], key2, ...]
            keys: List[bytes] = []
            if isinstance(res, (list, tuple)) and len(res) >= 2:
                for j in range(1, len(res), 2):
                    if isinstance(res[j], (bytes, bytearray)):
                        keys.append(bytes(res[j]))

            ids: List[int] = []
            for key in keys:
                # key like b"doc:123"
                try:
                    s = key.decode("utf-8")
                    ids.append(int(s.split(":")[-1]))
                except Exception:
                    continue
            if len(ids) < k:
                ids += [-1] * (k - len(ids))
            out[i] = np.array(ids[:k], dtype=np.int64)

        return EngineResult(ids=out)
