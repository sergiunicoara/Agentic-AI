# Performance benchmarks

This directory provides a minimal benchmark harness used to discuss scaling tradeoffs.

- `bench_retrieval.py`: measures retrieval latency distribution.

Example:

```bash
python -m benchmarks.bench_retrieval
```

In production you would use:
- k6/Locust load tests
- Prometheus histograms in live clusters
- Shadow traffic + A/B experiments for real-world tail latency
