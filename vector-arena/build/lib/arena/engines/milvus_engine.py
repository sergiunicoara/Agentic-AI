import os
import numpy as np
from .base import EngineResult

class MilvusEngine:
    name = "milvus"

    def __init__(self, dim: int):
        try:
            from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility
        except Exception as e:
            raise ImportError("pymilvus not installed. Install with: pip install pymilvus") from e

        self.dim = dim
        self._connections = connections
        self._FieldSchema = FieldSchema
        self._CollectionSchema = CollectionSchema
        self._DataType = DataType
        self._Collection = Collection
        self._utility = utility

        host = os.getenv("MILVUS_HOST", "localhost")
        port = os.getenv("MILVUS_PORT", "19530")
        self.collection = os.getenv("MILVUS_COLLECTION", "vector_arena_docs")

        connections.connect(alias="default", host=host, port=port)

        if utility.has_collection(self.collection):
            utility.drop_collection(self.collection)

        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
        ]
        schema = CollectionSchema(fields, description="vector arena benchmark")
        self._col = Collection(self.collection, schema=schema)

        # Create an HNSW index by default for reasonable performance
        index_params = {
            "index_type": os.getenv("MILVUS_INDEX_TYPE", "HNSW"),
            "metric_type": os.getenv("MILVUS_METRIC", "IP"),
            "params": {"M": 16, "efConstruction": 200},
        }
        self._col.create_index(field_name="vector", index_params=index_params)

    def build(self, docs: np.ndarray) -> None:
        ids = list(range(docs.shape[0]))
        self._col.insert([ids, docs.tolist()])
        self._col.flush()
        self._col.load()

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        search_params = {"params": {"ef": int(os.getenv("MILVUS_EF", "128"))}}
        res = self._col.search(
            data=queries.tolist(),
            anns_field="vector",
            param=search_params,
            limit=k,
            output_fields=["id"],
        )
        out = np.empty((len(res), k), dtype=np.int64)
        for i, hits in enumerate(res):
            ids = [int(h.id) for h in hits]
            if len(ids) < k:
                ids += [-1] * (k - len(ids))
            out[i] = np.array(ids[:k], dtype=np.int64)
        return EngineResult(ids=out)
