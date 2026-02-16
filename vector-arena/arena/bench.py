from __future__ import annotations

import argparse
import json
import os
import time
from typing import Dict, List, Any

import numpy as np
import faiss


def normalize(x: np.ndarray) -> np.ndarray:
    x = x.astype("float32")
    faiss.normalize_L2(x)
    return x


def recall_at_k(gt_ids: np.ndarray, pred_ids: np.ndarray, k: int) -> float:
    # pred_ids may contain -1 placeholders
    n = gt_ids.shape[0]
    acc = 0.0
    for i in range(n):
        gt = set(int(x) for x in gt_ids[i][:k].tolist())
        pr = set(int(x) for x in pred_ids[i][:k].tolist() if int(x) >= 0)
        acc += len(gt & pr) / float(k)
    return acc / float(n)


def percentiles(values_ms: List[float]) -> Dict[str, float]:
    if not values_ms:
        return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "mean_ms": 0.0}
    arr = np.array(values_ms, dtype=np.float64)
    return {
        "mean_ms": float(arr.mean()),
        "p50_ms": float(np.percentile(arr, 50)),
        "p95_ms": float(np.percentile(arr, 95)),
        "p99_ms": float(np.percentile(arr, 99)),
        "min_ms": float(arr.min()),
        "max_ms": float(arr.max()),
    }


def try_make_engine(name: str, dim: int):
    # Lazy imports so missing deps don't break everything.
    if name == "pinecone":
        from arena.engines.pinecone_engine import PineconeEngine
        return PineconeEngine(dim)
    if name == "chroma":
        from arena.engines.chroma_engine import ChromaEngine
        return ChromaEngine(dim)
    if name == "qdrant":
        from arena.engines.qdrant_engine import QdrantEngine
        return QdrantEngine(dim)
    if name == "weaviate":
        from arena.engines.weaviate_engine import WeaviateEngine
        return WeaviateEngine(dim)
    if name == "milvus":
        from arena.engines.milvus_engine import MilvusEngine
        return MilvusEngine(dim)
    if name == "redis":
        from arena.engines.redis_engine import RedisEngine
        return RedisEngine(dim)
    if name == "elasticsearch":
        from arena.engines.elasticsearch_engine import ElasticsearchEngine
        return ElasticsearchEngine(dim)
    if name == "opensearch":
        from arena.engines.opensearch_engine import OpenSearchEngine
        return OpenSearchEngine(dim)
    if name == "vespa":
        from arena.engines.vespa_engine import VespaEngine
        return VespaEngine(dim)
    if name == "typesense":
        from arena.engines.typesense_engine import TypesenseEngine
        return TypesenseEngine(dim)
    if name == "pgvector":
        from arena.engines.pgvector_engine import PgVectorEngine
        return PgVectorEngine(dim)
    if name == "scann":
        from arena.engines.scann_engine import ScannEngine
        return ScannEngine(dim)
    if name == "azure_ai_search":
        from arena.engines.azure_ai_search_engine import AzureAISearchEngine
        return AzureAISearchEngine(dim)
    if name == "vertex_ai_vector_search":
        from arena.engines.vertex_ai_vector_search_engine import VertexAIVectorSearchEngine
        return VertexAIVectorSearchEngine(dim)
    if name == "neo4j":
        from arena.engines.neo4j_engine import Neo4jEngine
        return Neo4jEngine(dim)
    if name == "clickhouse":
        from arena.engines.clickhouse_engine import ClickHouseEngine
        return ClickHouseEngine(dim)
    raise ValueError(f"Unknown engine: {name}")


def available_engine_names() -> List[str]:
    # "faiss_exact" is always included as ground truth/baseline
    return [
        "pinecone",
        "chroma",
        "qdrant",
        "weaviate",
        "milvus",
        "redis",
        "elasticsearch",
        "opensearch",
        "vespa",
        "typesense",
        "pgvector",
        "scann",
        "azure_ai_search",
        "vertex_ai_vector_search",
        "neo4j",
        "clickhouse",
    ]


def make_synth_random(n: int, d: int) -> np.ndarray:
    return normalize(np.random.randn(n, d))


def make_synth_clustered(n: int, d: int, n_clusters: int) -> np.ndarray:
    # More "embedding-like": sample cluster centers, then sample points around them
    centers = normalize(np.random.randn(n_clusters, d))
    # pick cluster id for each point
    cids = np.random.randint(0, n_clusters, size=(n,))
    x = centers[cids] + 0.15 * np.random.randn(n, d).astype("float32")
    return normalize(x)


def main() -> None:
    ap = argparse.ArgumentParser(description="Vector Arena benchmark across multiple vector DB backends.")
    ap.add_argument("--dim", type=int, default=int(os.getenv("DIM", "128")))
    ap.add_argument("--docs", type=int, default=int(os.getenv("DOCS", "100000")))
    ap.add_argument("--queries", type=int, default=int(os.getenv("QUERIES", "1000")))
    ap.add_argument("--k", type=int, default=int(os.getenv("K", "10")))
    ap.add_argument("--seed", type=int, default=int(os.getenv("SEED", "42")))
    ap.add_argument(
        "--dataset",
        type=str,
        default=os.getenv("DATASET", "random"),
        choices=["random", "clustered"],
        help="Synthetic dataset generator. 'random' is i.i.d. Gaussian; 'clustered' is a Gaussian mixture (more realistic for embeddings).",
    )
    ap.add_argument(
        "--clusters",
        type=int,
        default=int(os.getenv("CLUSTERS", "256")),
        help="Number of clusters for dataset='clustered'. Ignored for dataset='random'.",
    )
    ap.add_argument(
        "--data-cache-dir",
        type=str,
        default=os.getenv("DATA_CACHE_DIR", ""),
        help="Optional directory to cache generated docs/queries/gt for repeatable runs without regeneration. If empty, no caching.",
    )
    ap.add_argument("--force-regenerate", action="store_true", help="Ignore cached data and regenerate docs/queries/gt.")
    ap.add_argument(
        "--engines",
        type=str,
        default=os.getenv("ENGINES", "all"),
        help="Comma list like: pinecone,chroma,qdrant,weaviate,milvus or 'all'. Always includes faiss_exact baseline.",
    )
    ap.add_argument("--warmup", type=int, default=int(os.getenv("WARMUP", "2")), help="Warmup iterations per engine.")
    ap.add_argument(
        "--timed-runs",
        type=int,
        default=int(os.getenv("TIMED_RUNS", "5")),
        help="Timed runs per engine; timings are over the full query set per run.",
    )
    ap.add_argument(
        "--per-query-sample",
        type=int,
        default=int(os.getenv("PER_QUERY_SAMPLE", "25")),
        help="Number of per-query timings to sample (0 disables).",
    )
    ap.add_argument("--outdir", type=str, default=os.getenv("OUTDIR", "artifacts"))
    args = ap.parse_args()

    dim, n_docs, n_queries, k = args.dim, args.docs, args.queries, args.k

    # ----------------------------
    # Data generation / cache
    # ----------------------------
    cache_dir = args.data_cache_dir.strip()
    cache_enabled = bool(cache_dir)
    if cache_enabled:
        os.makedirs(cache_dir, exist_ok=True)
        tag = f"{args.dataset}_d{dim}_docs{n_docs}_q{n_queries}_k{k}_seed{args.seed}_c{args.clusters}"
        docs_path = os.path.join(cache_dir, f"docs_{tag}.npy")
        queries_path = os.path.join(cache_dir, f"queries_{tag}.npy")
        gt_path = os.path.join(cache_dir, f"gt_ids_{tag}.npy")
    else:
        docs_path = queries_path = gt_path = ""

    np.random.seed(args.seed)

    if (
        cache_enabled
        and (not args.force_regenerate)
        and os.path.exists(docs_path)
        and os.path.exists(queries_path)
        and os.path.exists(gt_path)
    ):
        docs = np.load(docs_path, mmap_mode="r")
        queries = np.load(queries_path, mmap_mode="r")
        gt_ids = np.load(gt_path, mmap_mode="r")
    else:
        if args.dataset == "random":
            docs = make_synth_random(n_docs, dim)
            queries = make_synth_random(n_queries, dim)
        else:
            docs = make_synth_clustered(n_docs, dim, args.clusters)
            queries = make_synth_clustered(n_queries, dim, max(8, args.clusters // 8))

        # Ground truth with exact inner product (cosine after normalization)
        gt = faiss.IndexFlatIP(dim)
        gt.add(np.asarray(docs, dtype="float32"))
        _, gt_ids = gt.search(np.asarray(queries, dtype="float32"), k)

        if cache_enabled:
            np.save(docs_path, np.asarray(docs, dtype="float32"))
            np.save(queries_path, np.asarray(queries, dtype="float32"))
            np.save(gt_path, np.asarray(gt_ids, dtype=np.int32))

    # Ensure we always have a GT index for the FAISS baseline runs
    gt = faiss.IndexFlatIP(dim)
    gt.add(np.asarray(docs, dtype="float32"))

    # ----------------------------
    # Benchmark
    # ----------------------------
    results: Dict[str, Any] = {}
    meta = {
        "dim": dim,
        "docs": n_docs,
        "queries": n_queries,
        "k": k,
        "seed": args.seed,
        "dataset": args.dataset,
        "clusters": args.clusters,
        "warmup": args.warmup,
        "timed_runs": args.timed_runs,
        "per_query_sample": args.per_query_sample,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Baseline: FAISS exact (also serves as GT)
    run_times = []
    pred = None
    for _ in range(max(1, args.timed_runs)):
        t0 = time.perf_counter()
        _, pred = gt.search(np.asarray(queries, dtype="float32"), k)
        run_times.append((time.perf_counter() - t0) * 1000.0)

    base = {
        "status": "ok",
        "build_ms": 0.0,
        "batch_latency_ms": percentiles(run_times),
        "qps_estimate": float(n_queries / (np.mean(run_times) / 1000.0)) if np.mean(run_times) > 0 else 0.0,
        "recall@k": 1.0,
    }
    results["faiss_exact"] = base

    # Select engines
    if args.engines.strip().lower() == "all":
        engine_names = available_engine_names()
    else:
        engine_names = [x.strip() for x in args.engines.split(",") if x.strip()]

    # Run each engine, with graceful skipping
    for name in engine_names:
        entry: Dict[str, Any] = {"status": "skipped"}
        try:
            engine = try_make_engine(name, dim)

            # Build
            t0 = time.perf_counter()
            engine.build(np.asarray(docs, dtype="float32"))
            build_ms = (time.perf_counter() - t0) * 1000.0

            # Warmup (batch search)
            for _ in range(max(0, args.warmup)):
                _ = engine.search(np.asarray(queries[: min(10, n_queries)], dtype="float32"), k)

            # Timed full-batch runs
            run_times = []
            pred_ids = None
            for _ in range(max(1, args.timed_runs)):
                t0 = time.perf_counter()
                pred_ids = engine.search(np.asarray(queries, dtype="float32"), k).ids
                run_times.append((time.perf_counter() - t0) * 1000.0)

            # Optional per-query sampling
            perq = []
            sample_n = max(0, min(args.per_query_sample, n_queries))
            if sample_n > 0:
                idx = np.linspace(0, n_queries - 1, sample_n).astype(int)
                for qi in idx:
                    t0 = time.perf_counter()
                    _ = engine.search(np.asarray(queries[qi : qi + 1], dtype="float32"), k)
                    perq.append((time.perf_counter() - t0) * 1000.0)

            entry = {
                "status": "ok",
                "build_ms": round(build_ms, 3),
                "batch_latency_ms": {kk: round(vv, 4) for kk, vv in percentiles(run_times).items()},
                "per_query_latency_ms_sample": {kk: round(vv, 4) for kk, vv in percentiles(perq).items()} if perq else None,
                "qps_estimate": round(float(n_queries / (np.mean(run_times) / 1000.0)), 4) if np.mean(run_times) > 0 else 0.0,
                "recall@k": round(float(recall_at_k(np.asarray(gt_ids), np.asarray(pred_ids), k)), 6) if pred_ids is not None else None,
            }
        except Exception as e:
            entry = {"status": "error", "error": f"{type(e).__name__}: {e}"}

        results[name] = entry

    out = {"meta": meta, "results": results}

    # ----------------------------
    # Write artifacts
    # ----------------------------
    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    # CSV summary for easy plotting
    csv_path = os.path.join(args.outdir, "results.csv")
    try:
        import csv

        with open(csv_path, "w", newline="", encoding="utf-8") as cf:
            w = csv.writer(cf)
            w.writerow(["engine", "status", "build_ms", "qps", "recall@k", "batch_p50_ms", "batch_p95_ms", "batch_p99_ms", "error"])
            for eng, v in results.items():
                bl = v.get("batch_latency_ms") or {}
                w.writerow(
                    [
                        eng,
                        v.get("status"),
                        v.get("build_ms", ""),
                        v.get("qps_estimate", ""),
                        v.get("recall@k", ""),
                        bl.get("p50_ms", ""),
                        bl.get("p95_ms", ""),
                        bl.get("p99_ms", ""),
                        v.get("error", "") if v.get("status") != "ok" else "",
                    ]
                )
    except Exception:
        pass

    # Simple Markdown report
    md_path = os.path.join(args.outdir, "results.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Vector Arena Benchmark Results\n\n")
        f.write("## Meta\n")
        for k_, v_ in meta.items():
            f.write(f"- **{k_}**: {v_}\n")
        f.write("\n## Results\n")
        for eng, v in results.items():
            f.write(f"### {eng}\n")
            f.write(f"- **status**: {v.get('status')}\n")
            if v.get("status") == "ok":
                f.write(f"- **build_ms**: {v.get('build_ms')}\n")
                f.write(f"- **qps_estimate**: {v.get('qps_estimate')}\n")
                f.write(f"- **recall@k**: {v.get('recall@k')}\n")
                f.write(f"- **batch_latency_ms**: {v.get('batch_latency_ms')}\n")
                if v.get("per_query_latency_ms_sample") is not None:
                    f.write(f"- **per_query_latency_ms_sample**: {v.get('per_query_latency_ms_sample')}\n")
            else:
                if v.get("error"):
                    f.write(f"- **error**: {v.get('error')}\n")
            f.write("\n")

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
