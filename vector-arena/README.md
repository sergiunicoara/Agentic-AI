# Vector Arena --- Single-Node Vector Database Benchmark

This repository contains a reproducible benchmark for comparing modern
vector databases and ANN systems on a single machine.

------------------------------------------------------------------------

## What This Benchmark Measures

-   Recall@k\
-   P50 / P95 / P99 latency\
-   QPS (queries per second)\
-   Recall vs latency tradeoffs\
-   Index build time

------------------------------------------------------------------------

## Reference Hardware

-   Intel i5-1135G7 (4C / 8T)\
-   24GB RAM\
-   NVMe SSD\
-   Single-node benchmark

------------------------------------------------------------------------

## Requirements

### System

-   Python 3.9+\
-   Docker + Docker Compose\
-   24GB RAM recommended

### Python dependencies

``` bash
pip install numpy pandas matplotlib scann faiss-cpu
```

------------------------------------------------------------------------

## Running the Benchmark

### Wave 1 --- Vector-native systems

``` bash
docker compose up -d qdrant weaviate redis postgres
```

``` bash
python -m arena.bench   --engines faiss_exact,scann,qdrant,weaviate,redis,pgvector   --dataset clustered   --docs 250000   --queries 1000   --dim 128   --k 10   --timed-runs 10   --data-cache-dir .cache
```

------------------------------------------------------------------------

### Wave 2 --- Search engines (run separately)

``` bash
docker compose down
docker compose up -d elasticsearch opensearch vespa
```

``` bash
python -m arena.bench   --engines elasticsearch,opensearch,vespa   --dataset clustered   --docs 250000   --queries 1000   --dim 128   --k 10   --timed-runs 10   --data-cache-dir .cache
```

------------------------------------------------------------------------

## Generate Plots

``` bash
python scripts/plot_results.py   --results artifacts/results.json   --out artifacts/plots
```

------------------------------------------------------------------------

# Key Findings

### 1️⃣ Significant Throughput Variance Across ANN Engines

Under identical workload conditions (250k vectors, dim=128, k=10, 10
timed runs):

-   Throughput varied by \~25× across ANN engines
    -   Redis: \~1,498 QPS\
    -   Elasticsearch: \~59 QPS

------------------------------------------------------------------------

### 2️⃣ Deterministic Baseline with Exact Search

-   FAISS (exact) achieved:
    -   100% recall@k
    -   \~3,824 QPS
    -   \~265 ms p95 latency

------------------------------------------------------------------------

### 3️⃣ Clear Recall--Latency Tradeoff

-   Elasticsearch achieved the highest ANN recall (0.76 recall@k)
    -   \~59 QPS\
    -   \~19.5s p95 latency
-   Weaviate delivered:
    -   \~5× higher throughput than Elasticsearch\
    -   \~4× lower p95 latency\
    -   at the cost of \~33% recall reduction

------------------------------------------------------------------------

### 4️⃣ Index Build-Time Variance

Index construction time ranged from:

-   Qdrant: \~63 seconds\
-   Vespa: \~59 minutes

A \~56× build-time variance under identical dataset conditions.

------------------------------------------------------------------------

# Operational Implications

-   Infrastructure selection must be empirical.
-   Recall constraints must be explicit for RAG correctness.
-   Index build-time impacts CI/CD velocity and recovery strategies.
-   Single-node results do not generalize to distributed scaling.
-   Unified adapter architecture enables vendor-neutral evaluation.
