# Cost & performance engineering

This repo now includes concrete artifacts for **measured performance**, **load/soak testing**, and **capacity planning**.

## What to measure

**Retrieval path (RAG first-stage):**
- p50 / p95 / p99 latency (end-to-end and per-stage)
- DB statement timeouts hit rate
- Cache hit rate
- SLO violation rate (rolling window)
- Shed/rate-limit rate (429)

**Indexing path (bulk/backfill):**
- docs/s
- chunks/s
- embedding provider TPS
- DB insert TPS (and lock waits)

## Load testing

Use k6 scenarios in `loadtest/k6/`.

```bash
k6 run \
  -e BASE_URL=http://localhost:8000 \
  -e WORKSPACE_ID=$WORKSPACE_ID \
  -e API_KEY=$API_KEY \
  -e RATE=50 -e DURATION=10m \
  loadtest/k6/retrieval.js
```

## Soak testing

A soak run produces **event-level JSONL** for offline analysis:

```bash
python -m benchmarks.soak.soak_ask \
  --base-url http://localhost:8000 \
  --workspace-id $WORKSPACE_ID --api-key $API_KEY \
  --qps 20 --duration-s 3600 \
  --out soak_ask.jsonl

python -m benchmarks.soak.analyze_soak --in soak_ask.jsonl
```

## Capacity planning (quick model)

Use `scripts/capacity_planner.py` to translate a workload into a pod count.

```bash
python scripts/capacity_planner.py --qps 150 --p95-ms 420 --cpu-ms-per-req 14
```

### Back-of-envelope model

- **Concurrency** ≈ QPS × p95_latency_seconds
- **CPU cores** ≈ QPS × cpu_ms_per_req / 1000
- **Pods** ≈ CPU_cores / (cores_per_pod × target_util)

Apply a **safety factor** (default 1.35) for p99, GC pauses, noisy neighbors, etc.

## Autoscaling economics

HPA should scale on a *leading* signal when possible:
- request concurrency (in-flight)
- queue depth (ingestion)
- DB saturation (connections, CPU)

Avoid scaling on latency alone (it is a lagging indicator and can destabilize).

## Cost levers

In priority order:
1. **Cache retrieval results** (already implemented in `app/retrieval/pipeline.py`)
2. **Reduce DB work**: statement timeouts, smaller candidate sets, shard fanout
3. **Batch embeddings** (bulk indexing already uses batch embeddings)
4. **Right-size reranking** (skip rerank when budget is low)
5. **Partition/vector index tuning** (see `app/vectorstore/pgvector_scaling.py`)
