import os
import json
from typing import Any, Dict, List

import numpy as np
import requests

from .base import EngineResult


class TypesenseEngine:
    """Typesense vector search.

    Requires Typesense v0.25+.
    """

    name = "typesense"

    def __init__(self, dim: int):
        self.dim = dim
        self.base_url = os.getenv("TYPESENSE_URL", "http://localhost:8108").rstrip("/")
        self.api_key = os.getenv("TYPESENSE_API_KEY", "xyz")
        self.collection = os.getenv("TYPESENSE_COLLECTION", "vector_arena")
        self.timeout = float(os.getenv("TYPESENSE_TIMEOUT", "30"))

        headers = {"X-TYPESENSE-API-KEY": self.api_key, "Content-Type": "application/json"}

        # Drop collection if exists
        requests.delete(
            f"{self.base_url}/collections/{self.collection}", headers=headers, timeout=self.timeout
        )

        schema = {
            "name": self.collection,
            "fields": [
                {"name": "id", "type": "int32"},
                # Vector field (float array)
                {"name": "v", "type": "float[]", "num_dim": int(dim)},
            ],
            "default_sorting_field": "id",
        }

        r = requests.post(
            f"{self.base_url}/collections",
            headers=headers,
            timeout=self.timeout,
            data=json.dumps(schema),
        )
        if r.status_code >= 300:
            raise RuntimeError(f"Failed to create Typesense collection: {r.status_code} {r.text}")

    def build(self, docs: np.ndarray) -> None:
        headers = {"X-TYPESENSE-API-KEY": self.api_key, "Content-Type": "text/plain"}
        batch = int(os.getenv("UPSERT_BATCH", "512"))
        for s in range(0, docs.shape[0], batch):
            e = min(s + batch, docs.shape[0])
            lines: List[str] = []
            for i in range(s, e):
                lines.append(json.dumps({"id": int(i), "v": docs[i].astype(np.float32).tolist()}))
            payload = "\n".join(lines)
            r = requests.post(
                f"{self.base_url}/collections/{self.collection}/documents/import?action=upsert",
                headers=headers,
                timeout=self.timeout,
                data=payload,
            )
            if r.status_code >= 300:
                raise RuntimeError(f"Typesense import failed: {r.status_code} {r.text}")

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        out = np.empty((queries.shape[0], k), dtype=np.int64)
        headers = {"X-TYPESENSE-API-KEY": self.api_key}
        for i in range(queries.shape[0]):
            vec = ",".join(f"{float(x):.8f}" for x in queries[i].astype(np.float32).tolist())
            params = {
                "q": "*",
                "query_by": "id",
                "per_page": int(k),
                "vector_query": f"v:([{vec}],k:{int(k)})",
                "include_fields": "id",
            }
            r = requests.get(
                f"{self.base_url}/collections/{self.collection}/documents/search",
                headers=headers,
                timeout=self.timeout,
                params=params,
            )
            if r.status_code >= 300:
                raise RuntimeError(f"Typesense search failed: {r.status_code} {r.text}")
            js = r.json()
            hits = js.get("hits") or []
            ids: List[int] = []
            for h in hits:
                doc = h.get("document") or {}
                try:
                    ids.append(int(doc.get("id")))
                except Exception:
                    continue
            if len(ids) < k:
                ids += [-1] * (k - len(ids))
            out[i] = np.array(ids[:k], dtype=np.int64)
        return EngineResult(ids=out)
