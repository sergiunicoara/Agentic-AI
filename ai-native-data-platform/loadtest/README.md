# Load & soak testing

This folder contains **operator-grade** load testing artifacts used to produce
repeatable tail-latency numbers for retrieval and ingestion.

## k6 quickstart

```bash
# Retrieval traffic at 50 rps for 5 minutes
k6 run \
  -e BASE_URL=http://localhost:8000 \
  -e WORKSPACE_ID=$WORKSPACE_ID \
  -e API_KEY=$API_KEY \
  -e RATE=50 -e DURATION=5m \
  loadtest/k6/retrieval.js

# Ingestion traffic at 10 rps for 5 minutes
k6 run \
  -e BASE_URL=http://localhost:8000 \
  -e WORKSPACE_ID=$WORKSPACE_ID \
  -e API_KEY=$API_KEY \
  -e RATE=10 -e DURATION=5m \
  loadtest/k6/ingest.js
```

## Soak testing

Soak tests are run using `benchmarks/soak/soak.py` which drives sustained mixed
traffic for hours and emits a JSON summary with p50/p95/p99 and error rates.

```bash
python -m benchmarks.soak.soak \
  --base-url http://localhost:8000 \
  --workspace-id $WORKSPACE_ID \
  --api-key $API_KEY \
  --duration-s 3600 \
  --rps 25 \
  --out soak_results.json
```
