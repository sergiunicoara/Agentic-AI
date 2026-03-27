# AI-Native Data Platform (Scale-oriented RAG scaffold)

This repository is a **platform-style** scaffold for building and operating Retrieval-Augmented Generation (RAG) systems at scale.
It is intentionally opinionated around the hiring signals you care about:

- **Retrieval architectures**: multi-stage retrieval (dense + lexical), fusion (RRF), reranking (MMR), embedding lifecycle/versioning.
- **Multimodal ingestion**: image and PDF visual page understanding via GPT-4o Vision / Gemini Vision — captions embedded and retrieved alongside text chunks.
- **Evaluation**: dataset-driven offline evaluation with RAGAS metrics, experiment configs, and CI-friendly quality/latency gates.
- **ML reliability**: explicit runtime contracts (SLO-inspired guardrails), groundedness checks, and structured observability/tracing.
- **Natural language query layer**: NLP → JSON → SQL pipeline so analysts can query the platform's data in plain English, without writing SQL.

## Architecture (high level)

- **Text ingestion pipeline** (`app/ingestion/pipeline.py`)
  - Idempotent chunking + embedding
  - Chunk-level dedupe via content hash
  - Embedding version tags to support re-embedding/migrations

- **Multimodal ingestion pipeline** (`app/ingestion/multimodal.py`)
  - Accepts images (PNG/JPG) and PDFs via `POST /ingest/image`
  - PDF pages converted to images via `pdf2image`
  - Each image captioned by vision model (GPT-4o / Gemini Vision / mock)
  - Captions embedded with the same model as text chunks — stored in `image_chunk`
  - Content-hash dedup; background worker mirrors text ingestion architecture

- **Retrieval stack** (`app/retrieval/*`)
  - Dense retriever (pgvector ANN on `document_chunk`)
  - Lexical retriever (Postgres full-text search)
  - Multimodal dense retriever — UNION across `document_chunk` + `image_chunk`, unified by cosine score
  - Fusion (Reciprocal Rank Fusion by default)
  - Reranking (MMR)
  - Each `RetrievedChunk` carries a `modality` field (`text` | `image`) for downstream handling
  - Trace persistence for offline debugging and eval sampling

- **Generation + groundedness** (`app/generation/*`)
  - Strict JSON schema outputs
  - Citation snippet verification + minimum evidence gate (works for both text and image captions)
  - Generation traces persisted to Postgres

- **Evaluation system** (`app/eval/*`)
  - Dataset: `app/eval/datasets/cases.jsonl`
  - Experiment configs: `app/eval/experiments/*.yaml`
  - Runner: `python -m app.eval.run --experiment ...`
  - RAGAS evaluation (`app/eval/ragas_eval.py`): faithfulness, answer_relevancy, context_precision, context_recall — supports mixed text/image corpora
  - Produces `artifacts/eval_summary.json` and fails with exit code 2 on gate violations

- **Reliability contracts** (`app/core/reliability/contracts.py`)
  - Latency SLO guardrails (P95 ≤ 800ms)
  - Empty-retrieval guardrails
  - Safe degradation to `unknown=true` responses on violations

- **Natural language query layer** (`app/nl_query/`)
  - `POST /query/natural-language` — plain English → SQL → results
  - PydanticAI extracts a structured `QueryIntent` (table, filters, aggregation, order, limit)
  - SQL builder produces parameterized queries; workspace scoping is always injected
  - Table/column whitelist + injection guard before any SQL reaches the DB
  - Hard `statement_timeout` per query; results capped at 1 000 rows
  - Every query written to `nl_query_audit_log` (generated SQL, params, latency, errors)

## Quickstart

```bash
docker compose up -d
psql postgresql://app:app@localhost:5432/app -f scripts/init_db.sql

# Terminal 1: text ingestion worker
python -m app.worker_main

# Terminal 2: API
uvicorn app.main:app --reload
```

Seeded demo credentials:
- `X-Workspace-Id: demo`
- `X-API-Key: demo`

## Multimodal ingestion

Ingest an image or a PDF (each page becomes a vision-captioned chunk):

```bash
# Single image
curl -X POST http://localhost:8000/ingest/image \
  -H "X-Workspace-Id: demo" \
  -H "X-API-Key: demo" \
  -F "file=@chart.png" \
  -F "source=report" \
  -F "external_id=fig-1"

# PDF — each page is captioned individually
curl -X POST http://localhost:8000/ingest/image \
  -H "X-Workspace-Id: demo" \
  -H "X-API-Key: demo" \
  -F "file=@report.pdf"
```

Response:

```json
{ "status": "queued", "page_count": 12 }
```

Configure the vision provider via environment variable:

```bash
VISION_PROVIDER=openai    # GPT-4o Vision
VISION_PROVIDER=gemini    # Gemini 1.5 Flash
VISION_PROVIDER=mock      # deterministic, no API key needed (default)
```

Enable unified text + image retrieval:

```bash
MULTIMODAL_RETRIEVAL=true
```

When enabled, `/ask` queries both `document_chunk` and `image_chunk` in a single ranked pass. Each result carries `modality: "text" | "image"` so citations can reference both sources.

## Natural language queries

Ask questions about the platform's own data in plain English:

```bash
curl -X POST http://localhost:8000/query/natural-language \
  -H "X-Workspace-Id: demo" \
  -H "X-API-Key: demo" \
  -H "Content-Type: application/json" \
  -d '{"workspace_id": "demo", "query": "Show me the 10 most recent failed ingestion runs"}'
```

Response includes the generated SQL for transparency:

```json
{
  "sql": "SELECT id, document_id, status, error, created_at FROM ingestion_run WHERE workspace_id = :_workspace_id AND status = :_v0 ORDER BY created_at DESC LIMIT 10",
  "results": [...],
  "row_count": 3
}
```

Queryable tables: `document`, `document_chunk`, `ingestion_run`, `trace_log`.
Sensitive tables (`workspace_api_key`) and write operations are not exposed.

Switch to real LLM intent extraction by setting `LLM_PROVIDER=openai` — falls back to a
deterministic mock when unset (safe for CI and local dev without an API key).

## Retrieval configuration

Key knobs (see `app/core/config.py`):

```bash
RETRIEVAL_MODE=hybrid          # dense | lexical | hybrid | multimodal
FUSION_METHOD=rrf              # rrf | concat
RERANK_MODE=mmr                # none | mmr
EMBEDDING_VERSION=v1
MULTIMODAL_RETRIEVAL=true      # include image_chunk in hybrid retrieval
VISION_PROVIDER=openai         # openai | gemini | mock
```

## Offline evaluation

Run a configured experiment:

```bash
python -m app.eval.run \
  --experiment app/eval/experiments/baseline.yaml \
  --cases app/eval/datasets/cases.jsonl \
  --json_out artifacts/eval_summary.json
```

Run RAGAS evaluation on a mixed-content corpus:

```python
from app.eval.ragas_eval import RagasTestCase, run_ragas_eval

results = run_ragas_eval([
    RagasTestCase(
        question="What does the Q3 chart show?",
        answer="Revenue grew 18% quarter-over-quarter.",
        contexts=["[image caption] Bar chart showing Q3 revenue at $4.2M, up from $3.6M in Q2."],
        ground_truth="Q3 revenue increased 18% vs Q2.",
    )
])
# results[0].faithfulness, .answer_relevancy, .context_precision, .context_recall
```

The runner enforces gates from the experiment config (pass rate, retrieval quality, P95 latency) and exits non-zero on violations.

## CI evaluation gates

GitHub Actions runs the same evaluation harness on every PR and on pushes to `main`:

- Workflow: `.github/workflows/eval-gates.yml`
- Spins up **pgvector/Postgres** via `docker compose`
- Seeds schema + demo workspace (`scripts/init_db.sql`)
- Executes `python -m app.eval.run ...`
- Uploads `artifacts/eval_summary.json` as a build artifact

This makes retrieval quality, groundedness checks, and latency budgets **non-negotiable deployment constraints**.

## Results snapshot

CI also renders a compact Markdown summary (`artifacts/results_snapshot.md`) from
`artifacts/eval_summary.json` and uploads it as a build artifact.

Locally, you can generate the snapshot after running eval:

```bash
python -m app.eval.render_results \
  --in_json artifacts/eval_summary.json \
  --out_md artifacts/results_snapshot.md
```

## What "scale" looks like here

This scaffold models the design patterns you'd use in a real AI-native platform:

- **Multi-stage retrieval**: cheap candidate generation + bounded expensive reranking
- **Multimodal unification**: text and image embeddings live in the same vector space — same retrieval path, same reranker, same groundedness checks
- **Separation of concerns**: ingestion, retrieval, generation, evaluation, and NL query as explicit subsystems
- **Lifecycle controls**: embedding versioning for safe migrations across text and image models
- **Operational signals**: structured traces (`trace_log`) and Prometheus metrics (`/metrics`)
- **Quality gates**: evaluation is treated as a deploy-time constraint, not an ad-hoc notebook
- **Text-to-SQL in production**: NL query layer inherits auth, rate limiting, audit logging, and workspace scoping from the existing platform — no separate infrastructure required

## Architecture diagram

```mermaid
flowchart LR
  Client -->|/ask| API[FastAPI API]
  Client -->|/query/natural-language| API
  Client -->|/ingest/image| API
  API -->|Auth+Rate limits| Router[A/B Experiment Router]
  Router --> R[Retrieval Pipeline]
  R -->|Dense ANN text| PG[(Postgres + pgvector)]
  R -->|Lexical FTS| PG
  R -->|Multimodal UNION| PG
  R -->|Cache| Redis[(Redis)]
  R -->|Traces| Trace[(trace_log)]
  R --> Gen[Grounded Generation]
  Gen -->|LLM Provider| LLM[(LLM)]
  Gen -->|Contracts| Guard[Groundedness & evidence checks]
  API -->|/ingest/transcript| Worker[Text Ingestion Worker]
  Worker -->|Embed chunks| Embed[(Embeddings)]
  Worker --> PG
  API -->|/ingest/image| MMWorker[Multimodal Ingestion Worker]
  MMWorker -->|Vision caption| Vision[(GPT-4o / Gemini Vision)]
  MMWorker -->|Embed caption| Embed
  MMWorker -->|image_chunk| PG
  API -->|NL query| NLQ[NL Query Layer]
  NLQ -->|PydanticAI intent| LLM
  NLQ -->|Parameterized SQL| PG
  NLQ -->|Audit log| Audit[(nl_query_audit_log)]
  API -->|metrics| Prom[Prometheus]
  Prom --> Alert[Alertmanager]
  API -->|online signals| Trace
  Drift[Cron drift monitor] --> Trace
```

## Scaling and deployment

See:

- `docs/deployment_k8s.md` for a Kubernetes deployment story (replicas, HPA, caching).
- `docs/multi_region.md` for a multi-region reference architecture (read-local routing, failover).
- `docs/replica_lag_routing.md` for replica lag handling and read/write routing logic.
- `k8s/istio/` for service mesh policies (mTLS, retries, outlier detection).
- `k8s/networkpolicy.yaml` for network topology hardening (default-deny, explicit allow).
- `ops/prometheus/alerts.yml` for an example alerting strategy using rolling SLO metrics.
- `k8s/` for example manifests.
