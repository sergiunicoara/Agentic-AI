# Embedding lifecycle operations (zero-downtime reindex)

This repo supports **blue/green embedding versions** via `document_chunk.embedding_version` and `workspace_index_state`.

## Key primitives

- `workspace_index_state.active_embedding_version`: what online retrieval uses.
- `workspace_index_state.target_embedding_version`: what you are currently backfilling.
- `workspace_index_state.index_epoch`: bump on cutover; used by strict consistency mode.

## Canary reads (pre-cutover)

Enable canary reads:

- `ALLOW_EMBEDDING_OVERRIDE=true`
- `ADMIN_TOKEN=<secret>`

Then send headers (or use k6 env vars):

- `X-Embedding-Version-Override: v2`
- `X-Admin-Token: <secret>`

This allows you to validate latency/quality before promoting `v2`.

## End-to-end reindex

Use:

```bash
python scripts/reindex/zero_downtime_reindex.py \
  --base-url http://localhost:8000 \
  --workspace demo --api-key demo \
  --target v2 \
  --rate 30 --duration 60 \
  --p95-ms 260 --err-rate 0.02
```

What it does:

1. Sets `target_embedding_version=v2`
2. Runs bulk backfill into `document_chunk` with `embedding_version=v2`
3. Runs a k6 canary that forces retrieval to use `v2`
4. If SLOs pass, promotes `target -> active` atomically
5. If SLOs fail, rolls back to previous `active` and clears the target

## Failure injection during backfill

`IndexingConfig` supports controlled transient failures:

- `fault_injection_rate`: probability of an injected flush failure
- `max_retries` / `max_backoff_ms`: retry policy

This is used to validate that the backfill is **resume-safe** and **idempotent**.
