# AI-Native Data Platform (Scale-oriented RAG scaffold)

This repository is a **platform-style** scaffold for building and operating Retrieval-Augmented Generation (RAG) systems at scale.
It is intentionally opinionated around the hiring signals you care about:

- **Retrieval architectures**: multi-stage retrieval (dense + lexical), fusion (RRF), reranking (MMR), embedding lifecycle/versioning.
- **Evaluation**: dataset-driven offline evaluation with experiment configs, CI-friendly quality/latency gates.
- **ML reliability**: explicit runtime contracts (SLO-inspired guardrails), groundedness checks, and structured observability/tracing.

## Architecture (high level)

- **Ingestion pipeline** (`app/ingestion/pipeline.py`)
  - Idempotent chunking + embedding
  - Chunk-level dedupe via content hash
  - Embedding version tags to support re-embedding/migrations

- **Retrieval stack** (`app/retrieval/*`)
  - Dense retriever (pgvector ANN)
  - Lexical retriever (Postgres full-text search)
  - Fusion (Reciprocal Rank Fusion by default)
  - Reranking (MMR)
  - Trace persistence for offline debugging and eval sampling

- **Generation + groundedness** (`app/generation/*`)
  - Strict JSON schema outputs
  - Citation snippet verification + minimum evidence gate
  - Generation traces persisted to Postgres

- **Evaluation system** (`app/eval/*`)
  - Dataset: `app/eval/datasets/cases.jsonl`
  - Experiment configs: `app/eval/experiments/*.yaml`
  - Runner: `python -m app.eval.run --experiment ...`
  - Produces `artifacts/eval_summary.json` and fails with exit code 2 on gate violations

- **Reliability contracts** (`app/core/reliability/contracts.py`)
  - Latency SLO guardrails
  - Empty-retrieval guardrails
  - Safe degradation to `unknown=true` responses on violations

## Quickstart

```bash
docker compose up -d
psql postgresql://app:app@localhost:5432/app -f scripts/init_db.sql

# Terminal 1: worker
python -m app.worker_main

# Terminal 2: API
uvicorn app.main:app --reload
```

Seeded demo credentials:
- `X-Workspace-Id: demo`
- `X-API-Key: demo`

## Retrieval configuration

Key knobs (see `app/core/config.py`):

```bash
export RETRIEVAL_MODE=hybrid     # dense | lexical | hybrid
export FUSION_METHOD=rrf        # rrf | concat
export RERANK_MODE=mmr          # none | mmr
export EMBEDDING_VERSION=v1
```

## Offline evaluation

Run a configured experiment:

```bash
python -m app.eval.run \
  --experiment app/eval/experiments/baseline.yaml \
  --cases app/eval/datasets/cases.jsonl \
  --json_out artifacts/eval_summary.json
```

The runner enforces gates from the experiment config (e.g. pass rate, retrieval quality, p95 latency) and exits non-zero on violations.

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

## What “scale” looks like here

This scaffold models the design patterns you’d use in a real AI-native platform:

- **Multi-stage retrieval**: cheap candidate generation + bounded expensive reranking
- **Separation of concerns**: ingestion, retrieval, generation, and evaluation as explicit subsystems
- **Lifecycle controls**: embedding versioning for safe migrations
- **Operational signals**: structured traces (`trace_log`) and Prometheus metrics (`/metrics`)
- **Quality gates**: evaluation is treated as a deploy-time constraint, not an ad-hoc notebook

## Architecture diagram

```mermaid
flowchart LR
  Client -->|/ask| API[FastAPI API]
  API -->|Auth+Rate limits| Router[A/B Experiment Router]
  Router --> R[Retrieval Pipeline]
  R -->|Dense ANN| PG[(Postgres + pgvector)]
  R -->|Lexical FTS| PG
  R -->|Cache| Redis[(Redis)]
  R -->|Traces| Trace[(trace_log)]
  R --> Gen[Grounded Generation]
  Gen -->|LLM Provider| LLM[(LLM)]
  Gen -->|Contracts| Guard[Groundedness & evidence checks]
  API -->|/ingest| Worker[Ingestion Worker]
  Worker -->|Embed chunks| Embed[(Embeddings)]
  Worker --> PG
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

