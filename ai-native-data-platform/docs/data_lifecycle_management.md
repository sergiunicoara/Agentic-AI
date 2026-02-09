# Data lifecycle management at scale

This platform treats **vector data** as a lifecycle-managed artifact:
- embedding versions evolve
- retrieval must remain available during reindex
- schema changes must be applied without stopping reads/writes

## Embedding reindexing (zero downtime)

### Control-plane state

`workspace_index_state` (see `ops/sql/001_workspace_index_state.sql`) tracks:
- `active_embedding_version`: served by retrieval
- `target_embedding_version`: being backfilled (shadow)
- `index_epoch`: bumped on cutover (used for strict consistency)

### Workflow

1. **Set target** embedding version (audit + resumability)
2. **Backfill** chunks tagged with the target version (`app/indexing/pipeline.py`)
3. **Promote** target to active atomically (`index_epoch += 1`)

Implementation: `app/indexing/lifecycle.py` + `scripts/reindex_embeddings.py`.

## Schema evolution under load

Guidelines:
- Additive changes first (new columns/tables)
- Backfill asynchronously (bulk pipeline)
- Switch reads (feature flag / version pointer)
- Remove old fields only after a safe window

## Retention & deletion

Recommended patterns:
- TTL or partition-drop for old chunks by embedding version
- Per-workspace hard delete: delete documents + chunks in background jobs, with rate limits

