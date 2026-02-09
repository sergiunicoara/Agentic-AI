# Distributed retrieval and sharding strategy

This scaffold supports **logical sharding** for retrieval.

## How it works here

- Configure `RETRIEVAL_SHARD_DSNS` as a comma-separated list of Postgres DSNs.
- The retrieval pipeline (`app/retrieval/pipeline.py`) will **fan-out** each retrieval stage to all shards and merge results.
- Results are de-duplicated by chunk id and re-ranked via fusion/reranking.

This approach is intentionally simple and is meant to demonstrate the platform interface.

## Production evolution

In production, you usually adopt one of these patterns:

1) **Query fan-out** (what this scaffold does)
   - Pros: simple, no router state
   - Cons: query cost scales with number of shards

2) **Document-based routing**
   - Partition documents by tenant/workspace and route queries only to the relevant shard.
   - Requires a shard map (consistent hashing or metadata service).

3) **Two-tier retrieval**
   - A small global index finds candidate shards (or coarse centroids), then the query is routed only to those shards.

## Why it matters

Distributed retrieval is one of the core scaling pressure points for AI-native data platforms: it impacts latency, cost, and operational blast radius.
