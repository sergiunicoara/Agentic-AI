# Runbook: Retrieval latency SLO

## SLO

- **Objective:** p95 `/ask` latency < `settings.max_request_latency_ms`
- **Retrieval sub-SLO:** p95 retrieval stage < `settings.retrieval_budget_ms`

## Primary signals

Prometheus metrics (see `ops/prometheus`):
- `http_request_latency_seconds_bucket{route="/ask"}`
- `http_requests_total{route="/ask"}`
- `rolling_slo_p95_latency_ms`
- `rolling_slo_unknown_rate`

## Triage checklist

1) **Is the issue localized?**
   - by workspace_id (check logs/traces) vs global (check cluster metrics)

2) **Cache health**
   - cache hit rate drop often precedes DB overload

3) **DB health**
   - replica lag / saturation
   - `statement_timeout` errors in logs

4) **Sharding/routing**
   - verify shard fanout and hedging settings

## Mitigations

- Reduce fanout: `RETRIEVAL_SHARD_FANOUT=1`
- Increase cache TTL for query embeddings
- Temporarily disable reranking: `RERANK_MODE=none`
- Enable safe-mode if needed (see reliability controller)

## Post-incident

- Fill `docs/postmortems/template.md`
- Add a regression test or eval gate for the failure mode
