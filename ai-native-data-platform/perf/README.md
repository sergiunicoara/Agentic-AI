# Performance baselines and regression gates

This repository treats **retrieval performance** as a first-class, testable contract.

## What lives here

- `perf/baselines/*.json`: k6 `--summary-export` baselines captured from a controlled environment.
- `scripts/perf/compare_k6_baseline.py`: CI-friendly baseline regression checker.
- `scripts/perf/plot_k6_summary.py`: optional plot generator (local or artifact generation).
- `reports/`: generated JSON summaries and plots (CI artifacts).

## Capture a baseline

1) Run the k6 scenario and export summary:

```bash
mkdir -p reports
k6 run loadtest/k6/retrieval.js \
  -e BASE_URL="http://localhost:8000" \
  -e WORKSPACE_ID="demo" \
  -e API_KEY="demo" \
  -e RATE=50 -e DURATION=2m \
  --summary-export=reports/k6_retrieval_summary.json
```

2) Promote it to the baseline (commit it):

```bash
cp reports/k6_retrieval_summary.json perf/baselines/retrieval.json
```

3) (Optional) Generate plots:

```bash
python scripts/perf/plot_k6_summary.py --summary reports/k6_retrieval_summary.json --name retrieval
```

## CI gate

The `loadtest-k6` GitHub Action exports a summary JSON and compares it to a committed baseline.

Default thresholds (in `scripts/perf/compare_k6_baseline.py`):
- `http_req_duration.p(95)`: max +10% regression
- `http_req_duration.p(99)`: max +10% regression
- `http_req_failed.rate`: max +25% regression

Adjust thresholds by editing `DEFAULT_THRESHOLDS`.
