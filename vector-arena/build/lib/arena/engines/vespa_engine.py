import os
import json
from typing import Any, Dict, List

import numpy as np
import requests

from .base import EngineResult


class VespaEngine:
    """Vespa approximate nearest neighbor search (HNSW).

    Notes:
    - Vespa requires an application package (schema) to be deployed before indexing/searching.
    - This adapter assumes the deployed schema includes:
        * document type: VESPA_DOC_TYPE (default 'doc')
        * a tensor field named 'v' representing the embedding
        * ANN enabled on 'v'

    Environment:
      VESPA_ENDPOINT: e.g. http://vespa:8080
      VESPA_SCHEMA: schema / document namespace, default 'vector_arena'
      VESPA_DOC_TYPE: document type, default 'doc'
    """

    name = "vespa"

    def __init__(self, dim: int):
        self.dim = dim
        self.endpoint = os.getenv("VESPA_ENDPOINT", "http://localhost:8080").rstrip("/")
        self.schema = os.getenv("VESPA_SCHEMA", "vector_arena")
        self.doc_type = os.getenv("VESPA_DOC_TYPE", "doc")
        self.timeout = float(os.getenv("VESPA_TIMEOUT", "30"))

    @staticmethod
    def _tensor_literal(vec: np.ndarray) -> Dict[str, Any]:
        # Vespa tensor (dense) as "values" list. Requires the schema to match the dimension.
        return {"values": np.asarray(vec, dtype=np.float32).tolist()}

    def build(self, docs: np.ndarray) -> None:
        batch = int(os.getenv("UPSERT_BATCH", "128"))
        # Feed documents
        for s in range(0, docs.shape[0], batch):
            e = min(s + batch, docs.shape[0])
            for i in range(s, e):
                docid = str(int(i))
                url = f"{self.endpoint}/document/v1/{self.schema}/{self.doc_type}/docid/{docid}"
                payload = {"fields": {"id": int(i), "v": self._tensor_literal(docs[i])}}
                r = requests.put(
                    url,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(payload),
                )
                if r.status_code >= 300:
                    raise RuntimeError(f"Vespa feed failed ({r.status_code}): {r.text}")

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        out = np.empty((queries.shape[0], k), dtype=np.int64)
        # YQL nearestNeighbor query; assumes schema contains 'v' tensor field.
        for i in range(queries.shape[0]):
            yql = f"select id from sources * where ([{{\"targetNumHits\":{int(k)}}}]nearestNeighbor(v, qv));"
            body = {
                "yql": yql,
                "hits": int(k),
                "ranking": {"profile": os.getenv("VESPA_RANK_PROFILE", "default")},
                "input": {"query(qv)": self._tensor_literal(queries[i])},
            }
            r = requests.post(
                f"{self.endpoint}/search/",
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
                data=json.dumps(body),
            )
            if r.status_code >= 300:
                raise RuntimeError(f"Vespa search failed ({r.status_code}): {r.text}")
            js = r.json()
            hits = (((js.get("root") or {}).get("children")) or [])
            ids: List[int] = []
            for h in hits:
                fields = h.get("fields") or {}
                try:
                    ids.append(int(fields.get("id")))
                except Exception:
                    # As fallback, try parsing Vespa document id
                    try:
                        docid = (h.get("id") or "").split("::")[-1]
                        ids.append(int(docid))
                    except Exception:
                        continue
            if len(ids) < k:
                ids += [-1] * (k - len(ids))
            out[i] = np.array(ids[:k], dtype=np.int64)
        return EngineResult(ids=out)
