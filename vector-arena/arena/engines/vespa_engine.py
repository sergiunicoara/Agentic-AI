import os
import json
from typing import Any, Dict, List, Optional

import numpy as np
import requests

from .base import EngineResult


class VespaEngine:
    name = "vespa"

    def __init__(self, dim: int):
        self.dim = dim

        self.endpoint = os.getenv("VESPA_ENDPOINT", "http://localhost:8080").rstrip("/")
        self.schema = os.getenv("VESPA_SCHEMA", "vector_arena")
        self.doc_type = os.getenv("VESPA_DOC_TYPE", "vector_arena")
        self.cluster = os.getenv("VESPA_CLUSTER", "content")

        self.vector_field = os.getenv("VESPA_VECTOR_FIELD", "vector")
        self.query_tensor_name = os.getenv("VESPA_QUERY_TENSOR_NAME", "qv")
        self.rank_profile = os.getenv("VESPA_RANK_PROFILE", "default")
        self.id_field = os.getenv("VESPA_ID_FIELD", "doc_id")

        self.timeout = float(os.getenv("VESPA_TIMEOUT", "30"))

        # Debug toggles
        self.debug_feed = os.getenv("VESPA_DEBUG_FEED", "0") == "1"
        self.debug_first_query = os.getenv("VESPA_DEBUG_FIRST_QUERY", "0") == "1"
        self._did_debug_query = False

    def _doc_url(self, docid: str) -> str:
        """
        Use UPDATE semantics with create=true so we can send field operations (assign).
        This matches what the endpoint is clearly expecting from the 400 error.
        """
        base = f"{self.endpoint}/document/v1/{self.schema}/{self.doc_type}/docid/{docid}"

        params = []
        if self.cluster:
            params.append(f"cluster={self.cluster}")
        params.append("create=true")  # allow update to create document

        return base + ("?" + "&".join(params) if params else "")

    def _assign(self, value: Any) -> Dict[str, Any]:
        return {"assign": value}

    def _tensor_values(self, vec: np.ndarray) -> Dict[str, Any]:
        """
        Dense tensor JSON using 'values'. Usually works fine for query tensors.
        """
        v = np.asarray(vec, dtype=np.float32).tolist()
        if len(v) != self.dim:
            raise ValueError(f"Vector dimension mismatch: expected {self.dim}, got {len(v)}")
        return {"values": v}

    def _tensor_cells_indexed(self, vec: np.ndarray, dim_name: str = "x") -> Dict[str, Any]:
        """
        Tensor JSON using 'cells' form (most compatible for document feeding).
          {"cells":[{"address":{"x":"0"},"value":0.1}, ... ]}
        """
        v = np.asarray(vec, dtype=np.float32).tolist()
        if len(v) != self.dim:
            raise ValueError(f"Vector dimension mismatch: expected {self.dim}, got {len(v)}")

        cells = [{"address": {dim_name: str(i)}, "value": float(val)} for i, val in enumerate(v)]
        return {"cells": cells}

    def build(self, docs: np.ndarray) -> None:
        """
        Feed docs using UPDATE+assign (as required by your endpoint),
        and feed tensor using CELLS inside assign.
        """
        idf = self.id_field
        vf = self.vector_field

        for i in range(int(docs.shape[0])):
            docid_int = int(i)
            docid = str(docid_int)
            url = self._doc_url(docid)

            payload: Dict[str, Any] = {
                "fields": {
                    # UPDATE API expects an operation object, not a bare number
                    idf: self._assign(docid_int),
                    # Assign tensor value; use cells form for feeding
                    vf: self._assign(self._tensor_cells_indexed(docs[i], dim_name="x")),
                }
            }

            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

            if self.debug_feed and docid_int == 0:
                print("\n[VESPA DEBUG FEED] PUT", url)
                print("[VESPA DEBUG FEED] Body (truncated):", body[:1400].decode("utf-8"), "\n")

            r = requests.put(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )

            if r.status_code >= 300:
                raise RuntimeError(f"Vespa feed failed ({r.status_code}): {r.text}")

    def _extract_int_id(self, hit: Dict[str, Any], id_field: str) -> Optional[int]:
        fields = hit.get("fields") or {}
        if id_field in fields:
            try:
                return int(fields[id_field])
            except Exception:
                return None

        vid = hit.get("id")
        if isinstance(vid, str) and "::" in vid:
            tail = vid.rsplit("::", 1)[-1]
            try:
                return int(tail)
            except Exception:
                return None

        return None

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        out = np.empty((int(queries.shape[0]), int(k)), dtype=np.int64)

        field = self.vector_field
        qname = self.query_tensor_name
        idf = self.id_field

        for i in range(int(queries.shape[0])):
            # Vespa NN annotation key: targetHits
            yql = (
                f"select {idf} from sources * where "
                f"([{{\"targetHits\":{int(k)}}}]nearestNeighbor({field}, {qname}));"
            )

            body: Dict[str, Any] = {
                "yql": yql,
                "hits": int(k),
                "ranking": {"profile": self.rank_profile},
                "input": {f"query({qname})": self._tensor_values(queries[i])},
            }

            r = requests.post(
                f"{self.endpoint}/search/",
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )

            if r.status_code >= 300:
                raise RuntimeError(f"Vespa search failed ({r.status_code}): {r.text}")

            js = r.json()

            if self.debug_first_query and not self._did_debug_query:
                self._did_debug_query = True
                print("\n[VESPA DEBUG QUERY] Request body:")
                print(json.dumps(body, indent=2)[:4000])
                print("\n[VESPA DEBUG QUERY] Response JSON (truncated):")
                print(json.dumps(js, indent=2)[:4000])
                print()

            hits = (((js.get("root") or {}).get("children")) or [])
            ids: List[int] = []

            for h in hits:
                hid = self._extract_int_id(h, idf)
                if hid is not None:
                    ids.append(hid)

            if len(ids) < k:
                ids += [-1] * (k - len(ids))

            out[i] = np.array(ids[:k], dtype=np.int64)

        return EngineResult(ids=out)
