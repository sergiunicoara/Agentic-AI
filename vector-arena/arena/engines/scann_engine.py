import numpy as np
from .base import EngineResult

class ScannEngine:
    """
    ScaNN (Google) ANN library wrapper.
    Notes:
      - Requires 'scann' package installed (pip install scann).
      - Uses cosine similarity if vectors are L2-normalized (recommended).
    """
    name = "scann"

    def __init__(self, dim: int):
        self.dim = dim
        self.searcher = None

    def build(self, docs: np.ndarray) -> None:
        try:
            import scann
        except Exception as e:
            raise ImportError("ScaNN is not installed. Install with: pip install scann") from e

        docs = np.asarray(docs, dtype=np.float32)
        # A reasonable default configuration. For serious benchmarking, sweep these knobs.
        self.searcher = scann.scann_ops_pybind.builder(docs, 10, "dot_product")             .tree(num_leaves=2000, num_leaves_to_search=100, training_sample_size=min(250000, docs.shape[0]))             .score_ah(2, anisotropic_quantization_threshold=0.2)             .reorder(100)             .build()

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        if self.searcher is None:
            raise RuntimeError("Index not built")
        queries = np.asarray(queries, dtype=np.float32)
        neighbors, _ = self.searcher.search_batched(queries, final_num_neighbors=k)
        return EngineResult(ids=np.asarray(neighbors, dtype=np.int64))
