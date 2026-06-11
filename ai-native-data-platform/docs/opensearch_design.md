# OpenSearch Integration — Design Decisions & Trade-offs

## Architecture

```
Ingestion:
  Document → Chunking → Embedding → PostgreSQL/pgvector
                                 ↘ OpenSearch (dual-write, best-effort)

Retrieval (runtime selectable via RETRIEVAL_MODE or experiment YAML):
  Query
    ├─ pgvector backend  → DenseRetriever + LexicalRetriever → RRF → rerank
    └─ OpenSearch backend
         ├─ BM25 only    → OpenSearchBM25Retriever
         ├─ Vector only  → OpenSearchVectorRetriever
         └─ Hybrid       → OpenSearchHybridRetriever (BM25 + kNN + RRF in Python)
                                                         ↓
                                               CrossEncoderStubReranker
```

## Decision log

### 1. RRF fusion in Python, not OpenSearch search pipeline

**Problem:** OpenSearch 2.x supports hybrid search natively via ML Commons search
pipelines (`normalization-processor`), but this requires ML Commons to be enabled
and a pipeline to be configured at index time — adding operational complexity and
an OpenSearch version dependency.

**Decision:** Implement RRF fusion in Python (`_rrf_fuse` in `opensearch_retriever.py`).
Both BM25 and kNN queries run in parallel threads, results are merged by rank.

**Trade-off:** One extra Python hop vs native OpenSearch fusion. For the typical
candidate set (25–50 docs), the Python overhead is < 1ms. Portability and
debuggability outweigh the micro-optimisation.

### 2. Lucene engine for kNN, not NMSLIB or Faiss

**Problem:** OpenSearch supports three kNN engines. NMSLIB requires a JNI layer
and has been deprecated since 2.12. Faiss offers better GPU performance at scale
but adds operational complexity (model loading, segment files).

**Decision:** Use Lucene engine with HNSW index (m=16, ef_construction=128).

**Trade-off:** Slightly lower raw throughput than Faiss at >10M vectors, but zero
additional dependencies, standard JVM GC, and the same query interface as BM25.
For a dev/portfolio environment with < 1M vectors, Lucene is the right choice.

### 3. Dual-write is best-effort, post-commit, and insert-gated

**Problem:** Making OpenSearch writes synchronous with Postgres commits creates a
distributed transaction problem — if OpenSearch is down, do we roll back Postgres?
And if the write happens inside the transaction, a slow OpenSearch holds a
Postgres connection open and OpenSearch can receive chunks from a transaction
that later rolls back.

**Decision:** The ingestion loop collects payloads for rows Postgres *actually
inserted* (`INSERT ... ON CONFLICT DO NOTHING RETURNING id` — on conflict,
RETURNING yields nothing and the chunk is skipped, since OpenSearch already has
it from the earlier run). After the transaction commits, the batch is pushed via
one `bulk_upsert`, wrapped in `try/except`. Failures are logged as
`opensearch_dual_write_failed` events but never propagate to the API response.

Additionally, the OpenSearch `_id` is deterministic —
`{document_id}:{chunk_index}:{embedding_version}` — matching the Postgres
conflict key, so even a redundant write overwrites in place instead of
duplicating. The `_source.chunk_id` field carries the Postgres uuid so retrieval
results reference the same ids as the pgvector backend.

**Trade-off:** Temporary inconsistency between Postgres and OpenSearch during
OpenSearch downtime. The client re-probes a down cluster every 30s
(`PROBE_COOLDOWN_S`), so dual-write self-heals after recovery; chunks missed
during the outage are repaired by backfill (`bulk_upsert` over a Postgres scan),
not by failing ingestion. This is the same pattern used by most dual-database
write paths in production (write primary, async mirror).

### 4. Workspace scoping as a filter, not index-level isolation

**Problem:** Multi-tenancy requires that workspace A cannot see workspace B's chunks.
Two approaches: separate indices per workspace, or a shared index with filter.

**Decision:** Shared index `ai_platform_chunks` with `workspace_id` as a `keyword`
filter on every query. This is enforced in all three retriever implementations —
the filter is never optional.

**Trade-off:** A shared index means index-level stats (e.g., IDF for BM25) are
computed across all workspaces, which can affect BM25 relevance for very small
workspaces. Separate indices would fix this but multiply operational complexity
linearly with tenant count. At portfolio scale, shared index is correct.

### 5. HNSW build parameters: m=16, ef_construction=128

**Problem:** HNSW graph quality is fixed at index time (m, ef_construction);
search-time breadth determines the recall/latency trade-off per query.

**Decision:** m=16, ef_construction=128 — the standard defaults that hit ~99%
recall@10 for 384-dim cosine vectors at < 5ms P99 on 100K vectors, single node.
Note the nmslib-only index setting `knn.algo_param.ef_search` is intentionally
absent: with the lucene engine, search-time candidate breadth follows the
query-level `k`, so the setting would be inert.

## Retrieval mode reference

| Mode | Config | Description |
|---|---|---|
| `dense` | `RETRIEVAL_MODE=dense` | pgvector ANN only |
| `lexical` | `RETRIEVAL_MODE=lexical` | Postgres FTS only |
| `hybrid` | `RETRIEVAL_MODE=hybrid` | pgvector + Postgres FTS + RRF |
| `opensearch_bm25` | experiment YAML | OpenSearch BM25 only |
| `opensearch_vector` | experiment YAML | OpenSearch kNN only |
| `opensearch_hybrid` | experiment YAML | OpenSearch BM25 + kNN + RRF (recommended) |
| `opensearch_hybrid_rerank` | experiment YAML | Separate BM25/vector stages → outer pipeline RRF |

## Running the evaluation

```bash
# Start OpenSearch
docker compose up -d opensearch

# Initialise index
python scripts/opensearch_init.py --wait

# Run pgvector baseline
python -m app.eval.run \
  --experiment app/eval/experiments/baseline.yaml \
  --cases app/eval/datasets/cases.jsonl \
  --json_out artifacts/pgvector_results.json

# Run OpenSearch hybrid
RETRIEVAL_MODE=opensearch_hybrid \
python -m app.eval.run \
  --experiment app/eval/experiments/opensearch_hybrid.yaml \
  --cases app/eval/datasets/cases.jsonl \
  --json_out artifacts/opensearch_results.json

# Compare
python -m app.eval.render_results \
  --in_json artifacts/pgvector_results.json \
  --out_md artifacts/pgvector_snapshot.md

python -m app.eval.render_results \
  --in_json artifacts/opensearch_results.json \
  --out_md artifacts/opensearch_snapshot.md
```

## GraphRAG extension (future)

See `app/retrieval/retrievers/graphrag_stub.py` for the full design.

Short version:
1. During ingestion, extract named entities from each chunk → write to Neo4j as
   `(Chunk)-[:MENTIONS]->(Entity)` edges.
2. At retrieval time, seed with OpenSearch hybrid (top-k chunks).
3. For each seed, traverse Neo4j 1–2 hops to find related chunks sharing entities.
4. Merge, deduplicate, rerank with cross-encoder.
5. This surfaces facts connected by relationships (e.g., "CEO of company X" → facts
   about company X) that pure vector similarity misses.

Implementation requires: `NEO4J_URL`, `neo4j` Python driver, entity extraction
model (spaCy or OpenAI function calling).

## Observability

Three new Prometheus metrics exported automatically:

| Metric | Type | Description |
|---|---|---|
| `opensearch_bm25_latency_seconds` | Histogram | BM25 query latency |
| `opensearch_vector_latency_seconds` | Histogram | kNN query latency |
| `opensearch_hybrid_latency_seconds` | Histogram | End-to-end hybrid (BM25 + kNN + RRF) |

All visible in the existing Grafana dashboard at `localhost:3000` once OpenSearch
traffic is generated.
