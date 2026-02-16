import os
import uuid
import numpy as np
from .base import EngineResult


class WeaviateEngine:
    name = "weaviate"

    def __init__(self, dim: int):
        try:
            import weaviate
            from weaviate.classes.config import Configure, Property, DataType
        except Exception as e:
            raise ImportError(
                "weaviate-client not installed. Install with: pip install weaviate-client"
            ) from e

        self.dim = dim
        self._weaviate = weaviate
        self._Configure = Configure
        self._Property = Property
        self._DataType = DataType

        host = os.getenv("WEAVIATE_HOST", "localhost")
        http_port = int(os.getenv("WEAVIATE_HTTP_PORT", "8080"))
        grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))

        self.collection = os.getenv("WEAVIATE_COLLECTION", "VectorArenaDoc")

        # Correct v4 local connection
        self._client = weaviate.connect_to_local(
            host=host,
            port=http_port,
            grpc_port=grpc_port,
        )

        # Clean benchmark run: delete collection if exists
        try:
            self._client.collections.delete(self.collection)
        except Exception:
            pass

        # Create collection (no vectorizer, we provide vectors)
        self._client.collections.create(
            name=self.collection,
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="i", data_type=DataType.INT),
            ],
        )

        self._col = self._client.collections.get(self.collection)

    def build(self, docs: np.ndarray) -> None:
        with self._col.batch.dynamic() as b:
            for i in range(docs.shape[0]):
                b.add_object(
                    properties={"i": int(i)},
                    vector=docs[i].tolist(),
                    uuid=str(uuid.UUID(int=i)),  # Valid deterministic UUID
                )

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        out = np.empty((queries.shape[0], k), dtype=np.int64)

        for qi in range(queries.shape[0]):
            res = self._col.query.near_vector(
                near_vector=queries[qi].tolist(),
                limit=k,
            )

            ids = []
            for obj in res.objects:
                try:
                    ids.append(int(uuid.UUID(str(obj.uuid))))
                except Exception:
                    ids.append(-1)

            if len(ids) < k:
                ids += [-1] * (k - len(ids))

            out[qi] = np.array(ids[:k], dtype=np.int64)

        return EngineResult(ids=out)

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass
