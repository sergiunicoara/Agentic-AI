import os
import time
from typing import List

import numpy as np

from .base import EngineResult

class PineconeEngine:
    name = "pinecone"

    def __init__(self, dim: int):
        try:
            from pinecone import Pinecone, ServerlessSpec
            from pinecone.exceptions import NotFoundException
        except Exception as e:
            raise ImportError("pinecone client not installed. Install with: pip install pinecone") from e

        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY is not set")

        self._pc = Pinecone(api_key=api_key)
        self._ServerlessSpec = ServerlessSpec
        self._NotFoundException = NotFoundException

        self.dim = dim
        self.index_name = os.getenv("PINECONE_INDEX", "vector-arena")
        self.namespace = os.getenv("PINECONE_NAMESPACE", "default")

        # region defaults
        self.cloud = os.getenv("PINECONE_CLOUD", "aws")
        self.region = os.getenv("PINECONE_REGION", "us-east-1")

        self._index = None

    def build(self, docs: np.ndarray) -> None:
        # Create index if missing, then upsert
        try:
            self._pc.describe_index(self.index_name)
        except Exception:
            self._pc.create_index(
                name=self.index_name,
                dimension=self.dim,
                metric="cosine",
                spec=self._ServerlessSpec(cloud=self.cloud, region=self.region),
            )

        # wait until ready
        while True:
            desc = self._pc.describe_index(self.index_name)
            if getattr(desc, "status", None) and getattr(desc.status, "ready", False):
                break
            time.sleep(1)

        self._index = self._pc.Index(self.index_name)

        # upsert in batches
        batch = int(os.getenv("UPSERT_BATCH", "200"))
        ids = [str(i) for i in range(docs.shape[0])]
        for s in range(0, docs.shape[0], batch):
            e = min(s + batch, docs.shape[0])
            vecs = [(ids[i], docs[i].tolist()) for i in range(s, e)]
            self._index.upsert(vectors=vecs, namespace=self.namespace)

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        if self._index is None:
            raise RuntimeError("Engine not built. Call build() first.")
        out = np.empty((queries.shape[0], k), dtype=np.int64)
        for i in range(queries.shape[0]):
            res = self._index.query(
                vector=queries[i].tolist(),
                top_k=k,
                include_values=False,
                namespace=self.namespace,
            )
            matches = getattr(res, "matches", []) or []
            ids = []
            for m in matches:
                try:
                    ids.append(int(m.id))
                except Exception:
                    # if id isn't numeric, drop into -1
                    ids.append(-1)
            if len(ids) < k:
                ids += [-1] * (k - len(ids))
            out[i] = np.array(ids[:k], dtype=np.int64)
        return EngineResult(ids=out)
