import os
import numpy as np
from .base import EngineResult


class QdrantEngine:
    name = "qdrant"

    def __init__(self, dim: int):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models
        except Exception as e:
            raise ImportError("qdrant-client not installed. Install with: pip install qdrant-client") from e

        self.dim = dim
        self._models = models

        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        self.collection = os.getenv("QDRANT_COLLECTION", "vector_arena_docs")
        self._client = QdrantClient(host=host, port=port)

        try:
            self._client.delete_collection(self.collection)
        except Exception:
            pass

        self._client.create_collection(
            collection_name=self.collection,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )

    def build(self, docs: np.ndarray) -> None:
        models = self._models
        batch = int(os.getenv("UPSERT_BATCH", "512"))
        for s in range(0, docs.shape[0], batch):
            e = min(s + batch, docs.shape[0])
            points = [
                models.PointStruct(id=int(i), vector=docs[i].tolist(), payload={"i": int(i)})
                for i in range(s, e)
            ]
            self._client.upsert(collection_name=self.collection, points=points)

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        out = np.empty((queries.shape[0], k), dtype=np.int64)
        for i in range(queries.shape[0]):
            res = self._client.query_points(
                collection_name=self.collection,
                query=queries[i].tolist(),
                limit=k,
                with_payload=False,
                with_vectors=False,
            )
            pts = getattr(res, "points", None) or []
            ids = [int(p.id) for p in pts]
            if len(ids) < k:
                ids += [-1] * (k - len(ids))
            out[i] = np.array(ids[:k], dtype=np.int64)
        return EngineResult(ids=out)
