import os
import numpy as np
from .base import EngineResult

class VertexAIVectorSearchEngine:
    """
    Vertex AI Vector Search (Matching Engine) wrapper.
    Requires env vars (one possible setup; adapt as needed):
      - GOOGLE_CLOUD_PROJECT
      - GOOGLE_CLOUD_REGION
      - VERTEX_INDEX_ENDPOINT_ID
      - VERTEX_DEPLOYED_INDEX_ID
    Assumes the index is already created and deployed.
    """
    name = "vertex_ai_vector_search"

    def __init__(self, dim: int):
        self.dim = dim
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT","")
        self.region = os.getenv("GOOGLE_CLOUD_REGION","")
        self.endpoint_id = os.getenv("VERTEX_INDEX_ENDPOINT_ID","")
        self.deployed_index_id = os.getenv("VERTEX_DEPLOYED_INDEX_ID","")
        if not (self.project and self.region and self.endpoint_id and self.deployed_index_id):
            raise RuntimeError("Missing Vertex env vars: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_REGION, VERTEX_INDEX_ENDPOINT_ID, VERTEX_DEPLOYED_INDEX_ID")
        self._endpoint = None

    def build(self, docs: np.ndarray) -> None:
        # This wrapper does not create the index; it only queries an already-deployed index.
        # Data ingestion should be done via Vertex batch upserts outside this benchmark.
        try:
            from google.cloud import aiplatform
        except Exception as e:
            raise ImportError("google-cloud-aiplatform not installed. Install with: pip install google-cloud-aiplatform") from e
        aiplatform.init(project=self.project, location=self.region)
        self._endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=self.endpoint_id)

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        if self._endpoint is None:
            raise RuntimeError("Endpoint not initialized. Did build() run?")
        queries = np.asarray(queries, dtype=np.float32)
        ids = np.full((queries.shape[0], k), -1, dtype=np.int64)
        for i, q in enumerate(queries):
            resp = self._endpoint.find_neighbors(
                deployed_index_id=self.deployed_index_id,
                queries=[q.tolist()],
                num_neighbors=k
            )
            row=[]
            for n in resp[0]:
                # neighbor.id is often a string; assume it's an int-like id
                try:
                    row.append(int(n.id))
                except Exception:
                    pass
            row = row[:k] + [-1]*(k-len(row))
            ids[i]=np.array(row,dtype=np.int64)
        return EngineResult(ids=ids)
