import os
import numpy as np
from .base import EngineResult

class AzureAISearchEngine:
    """
    Azure AI Search vector search wrapper.
    Requires env vars:
      - AZURE_SEARCH_ENDPOINT (e.g. https://<service>.search.windows.net)
      - AZURE_SEARCH_KEY
      - AZURE_SEARCH_INDEX (index name)
    The engine assumes the index already exists with a vector field.
    """
    name = "azure_ai_search"

    def __init__(self, dim: int):
        self.dim = dim
        self.endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "")
        self.key = os.getenv("AZURE_SEARCH_KEY", "")
        self.index = os.getenv("AZURE_SEARCH_INDEX", "")
        self._client = None
        if not (self.endpoint and self.key and self.index):
            raise RuntimeError("Missing Azure AI Search env vars: AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY, AZURE_SEARCH_INDEX")

    def build(self, docs: np.ndarray) -> None:
        # For fair benchmarking, you should create the index + vector configuration once,
        # then upload docs here. We implement a minimal uploader.
        try:
            from azure.core.credentials import AzureKeyCredential
            from azure.search.documents import SearchClient
        except Exception as e:
            raise ImportError("Azure SDK not installed. Install with: pip install azure-search-documents") from e

        self._client = SearchClient(endpoint=self.endpoint, index_name=self.index, credential=AzureKeyCredential(self.key))

        docs = np.asarray(docs, dtype=np.float32)
        batch = []
        for i, v in enumerate(docs):
            batch.append({"id": str(i), "vector": v.tolist()})
            if len(batch) >= 1000:
                self._client.upload_documents(batch)
                batch = []
        if batch:
            self._client.upload_documents(batch)

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        if self._client is None:
            raise RuntimeError("Client not initialized. Did build() run?")
        queries = np.asarray(queries, dtype=np.float32)
        ids = np.full((queries.shape[0], k), -1, dtype=np.int64)
        for qi, q in enumerate(queries):
            # Azure API uses 'vectorQueries' - exact syntax can vary by SDK version.
            results = self._client.search(
                search_text="",
                vector_queries=[{"vector": q.tolist(), "k": k, "fields": "vector"}],
                top=k
            )
            row=[]
            for r in results:
                try:
                    row.append(int(r["id"]))
                except Exception:
                    pass
            row = row[:k] + [-1]*(k-len(row))
            ids[qi]=np.array(row,dtype=np.int64)
        return EngineResult(ids=ids)
