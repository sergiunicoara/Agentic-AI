# Postmortem: Retrieval tail-latency spike during shard replica lag

- **Date:** 2026-02-07
- **Severity:** SEV2
- **Customer impact:** Elevated p95/p99 latency on `/ask` for ~18 minutes; no data loss.
- **Duration:** 12:14 – 12:32 UTC
- **Primary SLO(s) affected:** p95 `/ask` latency

## Summary

A read replica in shard-1 accumulated replay lag, causing query routing to send a portion of traffic to a slow/lagging node. This increased DB queuing time and pushed retrieval latency above the configured online budgets. Automatic remediation disabled adaptive routing and forced fanout to healthy shards.

## Impact

- p95 `/ask` latency: 1.6s (target < 0.8s)
- p99 `/ask` latency: 2.9s
- Error rate: unchanged

## Detection

- Prometheus alert: `AskLatencyP95High` fired
- Correlated signals:
  - `replica_lag_seconds` exceeded 2s threshold
  - DB timeouts increased (statement_timeout hits)

## Root cause

Routing policy chose a subset of shards (fanout=1) for efficiency. The chosen shard had a replica with lag and degraded performance. Hedging mitigated p99 but not p95 because the primary call consumed most of the budget before the hedge triggered.

## Contributing factors

- Lag health check interval too coarse (30s)
- Hedge delay set to 40ms; too conservative given observed tail

## Resolution

- Forced routing strategy to `fanout` via config toggle
- Reduced hedge delay to 15ms temporarily
- Restarted replica

## Corrective actions

### Immediate (this week)
- [ ] Tighten replica lag sampling interval to 5s
- [ ] Add routing decision logs with shard+replica chosen

### Medium (this month)
- [ ] Add adaptive hedge delay based on recent p95
- [ ] Add canary lane for routing policy changes

### Long term
- [ ] Per-shard queue depth signal integrated into router scoring

## What went well

- Alerts fired promptly
- Safe-mode degraded correctly (skipped rerank under budget pressure)

## What didn’t

- Hedge delay not calibrated
- Router lacked queue-depth input
