# Query routing under real load

When you have multiple read replicas and/or retrieval shards, routing matters more than the retrieval algorithm.

The goals are:

- keep p95/p99 latency stable under bursty load
- avoid stale replicas (lag)
- minimize cross-region traffic
- avoid thundering herds

## Routing primitives in this repo

### Deterministic shard selection (HRW / rendezvous hashing)

`app/retrieval/routing.py` supports selecting a deterministic subset of shards per query:

- `retrieval_routing_strategy=rendezvous`
- `retrieval_shard_fanout=N` to cap the number of shards queried

This is the baseline technique for scaling retrieval without fanning out to *every* shard.

### Strict consistency gating

If `shard_consistency_mode=strict`, the router checks `index_epoch` across shards before serving. If epochs diverge, retrieval fails closed rather than mixing inconsistent snapshots.

### Hedged requests (tail-latency protection)

In `app/retrieval/pipeline.py`, if fanout is 1 and multiple shards are available, the pipeline can issue a *hedged* request to a second shard after `shard_hedge_after_ms`.

This protects p95/p99 when a single shard is slow (GC, IO hiccup, noisy neighbor).

## What “real load” adds (and how to extend)

The repo keeps this layer lightweight. In production, “adaptive” routing is typically driven by:

- shard health (error rate)
- queue depth / connection pool saturation
- replica lag (WAL replay delay)
- per-shard p95 latency

Common extensions:

1. **Health registry**: a small in-memory / Redis store of per-shard EWMA stats.
2. **Adaptive fanout**: increase fanout when recall suffers; reduce when latency spikes.
3. **Overload shedding**: reject low-priority requests when budgets are exhausted.
4. **Read-local preference**: prefer same-region replicas (see `settings.region`).

The key platform idea is: retrieval quality is useless if the routing layer collapses under burst conditions.
