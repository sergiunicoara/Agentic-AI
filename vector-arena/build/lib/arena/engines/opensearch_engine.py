import os
import json
from typing import Any, Dict, List

import numpy as np
import requests

from .base import EngineResult


class OpenSearchEngine:
    """OpenSearch k-NN plugin (HNSW via nmslib).

    Designed for opensearchproject/opensearch 2.x with the k-NN plugin enabled.
    """

    name = "opensearch"

    def __init__(self, dim: int):
        self.dim = dim
        self.base_url = os.getenv("OPENSEARCH_URL", "http://localhost:9200").rstrip("/")
        self.index = os.getenv("OPENSEARCH_INDEX", "vector_arena")
        self.timeout = float(os.getenv("OPENSEARCH_TIMEOUT", "30"))

        auth_user = os.getenv("OPENSEARCH_USER")
        auth_pass = os.getenv("OPENSEARCH_PASSWORD")
        self._auth = (auth_user, auth_pass) if auth_user and auth_pass else None

        # Recreate index
        requests.delete(f"{self.base_url}/{self.index}", auth=self._auth, timeout=self.timeout)

        m = int(os.getenv("OPENSEARCH_HNSW_M", "16"))
        efc = int(os.getenv("OPENSEARCH_HNSW_EF_CONSTRUCTION", "128"))

        mapping = {
            "settings": {
                "index": {
                    "knn": True,
                    "number_of_shards": int(os.getenv("OPENSEARCH_SHARDS", "1")),
                    "number_of_replicas": int(os.getenv("OPENSEARCH_REPLICAS", "0")),
                }
            },
            "mappings": {
                "properties": {
                    "id": {"type": "integer"},
                    "v": {
                        "type": "knn_vector",
                        "dimension": dim,
                        "method": {
                            "name": "hnsw",
                            "engine": "nmslib",
                            "space_type": "cosinesimil",
                            "parameters": {"m": m, "ef_construction": efc},
                        },
                    },
                }
            },
        }

        r = requests.put(
            f"{self.base_url}/{self.index}",
            auth=self._auth,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"},
            data=json.dumps(mapping),
        )
        if r.status_code >= 300:
            raise RuntimeError(f"Failed to create OpenSearch index: {r.status_code} {r.text}")

    def build(self, docs: np.ndarray) -> None:
        batch = int(os.getenv("UPSERT_BATCH", "512"))
        for s in range(0, docs.shape[0], batch):
            e = min(s + batch, docs.shape[0])
            lines: List[str] = []
            for i in range(s, e):
                lines.append(json.dumps({"index": {"_index": self.index, "_id": int(i)}}))
                lines.append(json.dumps({"id": int(i), "v": docs[i].astype(np.float32).tolist()}))
            payload = "\n".join(lines) + "\n"
            r = requests.post(
                f"{self.base_url}/_bulk?refresh=false",
                auth=self._auth,
                timeout=self.timeout,
                headers={"Content-Type": "application/x-ndjson"},
                data=payload,
            )
            if r.status_code >= 300:
                raise RuntimeError(f"OpenSearch bulk insert failed: {r.status_code} {r.text}")

        r = requests.post(f"{self.base_url}/{self.index}/_refresh", auth=self._auth, timeout=self.timeout)
        if r.status_code >= 300:
            raise RuntimeError(f"OpenSearch refresh failed: {r.status_code} {r.text}")

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        out = np.empty((queries.shape[0], k), dtype=np.int64)
        for i in range(queries.shape[0]):
            body: Dict[str, Any] = {
                "size": int(k),
                "_source": False,
                "query": {"knn": {"v": {"vector": queries[i].astype(np.float32).tolist(), "k": int(k)}}},
            }
            r = requests.post(
                f"{self.base_url}/{self.index}/_search",
                auth=self._auth,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
                data=json.dumps(body),
            )
            if r.status_code >= 300:
                raise RuntimeError(f"OpenSearch search failed: {r.status_code} {r.text}")
            js = r.json()
            hits = (((js.get("hits") or {}).get("hits")) or [])
            ids: List[int] = []
            for h in hits:
                try:
                    ids.append(int(h.get("_id")))
                except Exception:
                    continue
            if len(ids) < k:
                ids += [-1] * (k - len(ids))
            out[i] = np.array(ids[:k], dtype=np.int64)
        return EngineResult(ids=out)
