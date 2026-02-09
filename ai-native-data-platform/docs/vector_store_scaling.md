# Vector store scaling strategies (pgvector)

This repo uses Postgres + **pgvector** as the reference vector store.

For small/medium deployments, a single `document_chunk` table works. At large scale (millions → billions of chunks), you need explicit strategies around:

- partitioning
- index selection/build policies
- write amplification control
- vacuum/analyze and storage hygiene

The module `app/vectorstore/pgvector_scaling.py` contains idempotent helpers you can wire into migrations or maintenance jobs.

## 1) Partitioning

Use **hash partitioning** to keep indexes and vacuum work bounded:

- Partition key: `workspace_id` (naturally enforces tenant locality)
- Target partition size: keep each partition under ~25M rows

In this repo:

- `ensure_partitions(partitions=N)` will create `document_chunk_p0...pN-1` as hash partitions.

## 2) Index type choice

Two common pgvector options:

### HNSW
- Better recall/latency for online retrieval.
- Higher build cost, bigger index.
- Tune: `m`, `ef_construction`.

### IVFFLAT
- Cheaper index, good throughput.
- Requires `ANALYZE` and a well-chosen `lists`.
- Tune: `lists` ~ sqrt(N) (rough heuristic).

In this repo:

- `ensure_vector_indexes(index_type="hnsw", m=16, ef_construction=64)`
- `ensure_vector_indexes(index_type="ivfflat", lists=...)`

## 3) Embedding lifecycle

`document_chunk` stores `embedding_version`. This allows:

- write-new-embeddings alongside old embeddings
- controlled rollouts by switching `settings.embedding_version`
- safe rollback by flipping the version back

## 4) Write amplification controls

Pragmatic tricks that matter at scale:

- batch inserts (see `app/indexing/pipeline.py`)
- keep `statement_timeout` non-zero during peak hours
- avoid rebuilding indexes during heavy ingest

## 5) Maintenance

At minimum:

- `ANALYZE document_chunk` after large ingests
- consider periodic VACUUM based on bloat

In this repo:

- `analyze_table()` is provided as a minimal hook.

## Production extensions

If you want to take this beyond a reference implementation, typical next steps are:

- dual-write to specialized vector infra (e.g., Faiss/ScaNN service, dedicated vector DB)
- tiered storage (hot vs cold chunks)
- background reindex jobs with throttling and tenant fairness