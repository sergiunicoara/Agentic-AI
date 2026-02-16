import os
import numpy as np
from .base import EngineResult

class ChromaEngine:
    name = "chroma"

    def __init__(self, dim: int):
        try:
            import chromadb
            from chromadb.config import Settings
        except Exception as e:
            raise ImportError("chromadb not installed. Install with: pip install chromadb") from e

        self.dim = dim
        self._chromadb = chromadb
        self._Settings = Settings

        self.collection_name = os.getenv("CHROMA_COLLECTION", "vector_arena_docs")
        # In-memory by default (no persistence); set CHROMA_PERSIST_DIR to persist.
        persist_dir = os.getenv("CHROMA_PERSIST_DIR")
        if persist_dir:
            self._client = chromadb.PersistentClient(path=persist_dir, settings=Settings(anonymized_telemetry=False))
        else:
            self._client = chromadb.Client(Settings(anonymized_telemetry=False))

        # recreate collection for clean benchmark run
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._col = self._client.create_collection(name=self.collection_name, metadata={"hnsw:space": "cosine"})

    def build(self, docs: np.ndarray) -> None:
        ids = [str(i) for i in range(docs.shape[0])]
        # chroma expects python lists
        batch = int(os.getenv("UPSERT_BATCH", "500"))
        for s in range(0, docs.shape[0], batch):
            e = min(s + batch, docs.shape[0])
            self._col.add(
                ids=ids[s:e],
                embeddings=docs[s:e].tolist(),
                metadatas=[{"i": int(i)} for i in range(s, e)],
                documents=[f"doc_{i}" for i in range(s, e)],
            )

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        res = self._col.query(query_embeddings=queries.tolist(), n_results=k, include=["distances"])
        ids = res.get("ids", [])
        out = np.array([[int(x) for x in row] for row in ids], dtype=np.int64)
        return EngineResult(ids=out)
