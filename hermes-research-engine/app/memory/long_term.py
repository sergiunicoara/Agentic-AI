"""LanceDB-backed long-term vector memory using HuggingFace Inference API for embeddings."""
from __future__ import annotations

import os
from typing import List

import lancedb
import numpy as np
import pyarrow as pa
from openai import OpenAI

# HF Inference Providers support OpenAI-compatible /v1/embeddings
_EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
_EMBED_DIM = 384
_DB_PATH = os.getenv("LANCEDB_PATH", "./data/vector_store")
_TABLE = "documents"

_SCHEMA = pa.schema(
    [
        pa.field("id", pa.utf8()),
        pa.field("text", pa.utf8()),
        pa.field("source", pa.utf8()),
        pa.field("vector", pa.list_(pa.float32(), _EMBED_DIM)),
    ]
)


def _make_embed_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["HF_TOKEN"],
        base_url=os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1"),
    )


class LongTermMemory:
    def __init__(self) -> None:
        self._db = lancedb.connect(_DB_PATH)
        self._embed_client: OpenAI | None = None
        if _TABLE in self._db.table_names():
            self._table = self._db.open_table(_TABLE)
        else:
            self._table = self._db.create_table(_TABLE, schema=_SCHEMA)

    @property
    def embed_client(self) -> OpenAI:
        if self._embed_client is None:
            self._embed_client = _make_embed_client()
        return self._embed_client

    def _embed(self, text: str) -> List[float]:
        resp = self.embed_client.embeddings.create(model=_EMBED_MODEL, input=text)
        return resp.data[0].embedding

    def ingest(self, doc_id: str, text: str, source: str = "") -> None:
        vector = self._embed(text)
        self._table.add([{"id": doc_id, "text": text, "source": source, "vector": vector}])

    def search(self, query: str, k: int = 5) -> List[dict]:
        vec = self._embed(query)
        results = (
            self._table.search(vec)
            .limit(k)
            .select(["id", "text", "source"])
            .to_list()
        )
        return results

    def similarity_score(self, query: str, candidate: str) -> float:
        a = np.array(self._embed(query))
        b = np.array(self._embed(candidate))
        return float(np.dot(a, b))


long_term_memory = LongTermMemory()
