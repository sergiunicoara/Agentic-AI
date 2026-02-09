from __future__ import annotations

import statistics
import time

from app.providers.embeddings import embed
from app.retrieval.factory import build_pipeline


def bench(workspace_id: str = "demo", query: str = "onboarding", n: int = 200) -> dict:
    pipeline = build_pipeline("baseline")
    qvec = embed(query)
    lats = []
    for _ in range(n):
        t0 = time.time()
        _, ms = pipeline.run(workspace_id, query, query_vec=qvec, k=5, rerank_candidates=25)
        lats.append(float(ms) if ms else (time.time() - t0) * 1000)

    lats_sorted = sorted(lats)
    def pct(p: float) -> float:
        if not lats_sorted:
            return 0.0
        idx = int(round((p / 100.0) * (len(lats_sorted) - 1)))
        idx = max(0, min(len(lats_sorted) - 1, idx))
        return float(lats_sorted[idx])

    return {
        "n": n,
        "mean_ms": float(statistics.mean(lats)) if lats else 0.0,
        "p50_ms": pct(50),
        "p95_ms": pct(95),
        "max_ms": float(max(lats)) if lats else 0.0,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(bench(), indent=2))
