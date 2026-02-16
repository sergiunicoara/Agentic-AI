# Vector Arena --- Single-Node Vector Database Benchmark

This repository contains a reproducible benchmark for comparing modern
vector databases and ANN systems on a single machine.

## What This Benchmark Measures

-   Recall@k
-   P50 / P95 / P99 latency
-   QPS (queries per second)
-   Recall vs latency tradeoffs

------------------------------------------------------------------------

## Reference Hardware

-   Intel i5-1135G7 (4C / 8T)
-   24GB RAM
-   NVMe SSD
-   Single-node benchmark

------------------------------------------------------------------------

## Requirements

### System

-   Python 3.9+
-   Docker + Docker Compose
-   24GB RAM recommended

### Python dependencies

``` bash
pip install numpy pandas matplotlib scann faiss-cpu
```

------------------------------------------------------------------------

## Running the Benchmark

### Wave 1 -- Vector-native systems

``` bash
docker compose up -d qdrant weaviate redis postgres
```

``` bash
python -m arena.bench   --engines faiss_exact,scann,qdrant,weaviate,redis,pgvector   --dataset clustered   --docs 250000   --queries 1000   --dim 128   --k 10   --timed-runs 10   --data-cache-dir .cache
```

------------------------------------------------------------------------

### Wave 2 -- Search engines (run separately)

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

## Notes

-   Single-node benchmark
-   Default/light tuning
-   Synthetic clustered dataset
-   Not a distributed scaling benchmark
-   Not cost-normalized
