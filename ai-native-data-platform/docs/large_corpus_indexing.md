# Large corpus indexing pipelines

This repo has two ingestion/indexing paths:

1. **Online ingestion** (`app/ingestion/*`): small, synchronous-ish, optimized for correctness and idempotency.
2. **Bulk indexing / backfill** (`app/indexing/*`): optimized for throughput, checkpointing, and embedding lifecycle backfills.

## Why a separate bulk pipeline

Large corpora introduce constraints that the online path intentionally avoids:

- **Throughput**: amortize embedding overhead via batching.
- **Checkpointing**: restartability without reprocessing the whole dataset.
- **Backfills**: re-index when `embedding_version` changes.
- **Operational safety**: DB statement timeouts, bounded memory.

## Design

### Manifest-driven execution

`build_manifest(workspace_id)` materializes a `jsonl` file of document ids. The manifest is:

- reproducible (audit artifact)
- append-only
- shardable (split by line ranges)

### Two-stage batching

In `run_manifest(...)`:

1. Fetch documents in **doc batches** (`batch_size_docs`).
2. Chunk and embed in **embedding batches** (`embedding_batch_size`) using `embed_batch(...)`.
3. Insert chunks in **DB batches** (`batch_size_chunks`) with `ON CONFLICT DO NOTHING` for idempotency.

### Idempotency and embedding lifecycle

`document_chunk` uses `(document_id, chunk_index, embedding_version)` as the logical uniqueness key.

- Backfilling a new `embedding_version` writes alongside old versions.
- Rollbacks are handled at query time via `WHERE embedding_version = :embedding_version`.

## How to run

```bash
python scripts/run_bulk_index.py --workspace <workspace_id> --build-manifest
python scripts/run_bulk_index.py --workspace <workspace_id> --manifest data/index_manifests/<manifest>.jsonl
```

## Scaling out (production notes)

For true multi-node indexing, you typically add:

- a **task table** (manifest chunks -> workers)
- distributed locks / leases
- a dead-letter queue
- multi-tenant rate limits

The code here is kept dependency-light, but the pipeline boundaries are chosen to map directly onto that design.
