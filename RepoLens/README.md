# Codex — Code Documentation Assistant

Codex is a repo-agnostic code assistant for asking natural-language questions about a Python or Markdown codebase. It indexes source into Postgres + pgvector, retrieves AST-aware chunks, streams answers through Claude, and returns only server-validated citations as clickable source links.

The default demo corpus is `fastapi/fastapi`, indexed to the `fastapi/` package directory.

## Quick start

Requirements: Docker Desktop with Compose and API keys for Anthropic and OpenAI.

```powershell
Copy-Item .env.example .env
# Fill ANTHROPIC_API_KEY and OPENAI_API_KEY in .env
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000).

Index a repository from another terminal:

```powershell
docker compose run --rm api python -m app.ingest https://github.com/fastapi/fastapi.git --subdir fastapi
```

The ingestion command accepts a GitHub URL or local path, respects `.gitignore`, parses Python with Tree-sitter, splits Markdown on headings, embeds chunks in batches, and records exact source content for citation viewing.

Useful commands:

```powershell
make test
make lint
make eval-ingest
make eval
make eval-hybrid
docker compose down
```

## Product value

- Answers stream through a Next.js frontend.
- Claims may include citations such as `fastapi/routing.py:3133-3244`.
- Only citations returned by the backend validation step open the source viewer; other citation-shaped text remains plain text.
- Chat deltas are delivered progressively. The final `done.final_text` is the backend-accepted answer after citation validation, so an uncited factual answer can be replaced safely.
- The repository map exposes files and parsed Python symbols.
- The same retrieval and browsing modules are available through MCP for Claude Code.

## Architecture

```text
Next.js frontend ──SSE──> FastAPI ──> shared retrieval service ──> Postgres + pgvector
                              │                    │
                              │                    └──> Claude Sonnet
                              └──> repo map / file viewer / eval API

FastMCP stdio server ────────> shared retrieval and browsing modules
Ingestion CLI ───────────────> Postgres + pgvector
Observability ───────────────> OpenTelemetry; optional Langfuse on LLM calls
```

Backend modules are organized by responsibility:

- `app/ingest`: source resolution, walking, parsing, chunking, embeddings, and upsert.
- `app/retrieval`: vector search, context assembly, streaming chat, memory, and citations.
- `app/browse`: repository map and exact file content endpoints.
- `app/evals`: golden-set runner, objective metrics, and LLM judges.
- `app/mcp_server.py`: FastMCP tools backed by shared retrieval and browse modules.

## Data model and citation fidelity

Postgres stores repositories, files, chunks, and conversation messages. Each chunk records its `symbol_path`, `kind`, exact 1-indexed `start_line`/`end_line`, content, embedding, and token count.

Python chunks are emitted at module, class, function, and method boundaries. Long chunks are split only on line boundaries. Source files are read as bytes before line slicing so CRLF files retain exact citation fidelity. Tests verify that stored chunk ranges reproduce the original source.

## MCP / Claude Code

The committed `.mcp.json` starts the server over stdio through Docker Compose. Claude Code can discover:

- `search_code(repo_id, query, top_k)`
- `get_file(repo_id, path)`
- `get_repo_map(repo_id)`

The MCP server uses the same retrieval code as the HTTP API; there is no second implementation to drift.

## Evaluation

The full golden set is in `evals/golden.yaml` and contains 30 hand-written questions, including three refusal cases. Automatic CI runs deterministic objective metric and judge tests; the complete FastAPI evaluation is manual and credential-dependent.

Previously verified full evaluation against the FastAPI demo repository (historical; these
numbers predate the current answer-correctness and citation-coverage metrics):

| Metric | Result | Gate |
|---|---:|---:|
| retrieval_hit@5 | 1.00 | ≥ 0.80 |
| citation_precision | 0.85 | ≥ 0.85 |
| groundedness | 0.99 | ≥ 0.70 |
| refusal_accuracy | 1.00 | = 1.00 |
| p95 latency | 14.29s | report only |

Vector-only retrieval is the default. BM25 + Reciprocal Rank Fusion was measured and rejected because it reduced retrieval hit rate, reduced citation precision, and increased latency:

| Configuration | retrieval_hit@5 | citation_precision | p95 latency |
|---|---:|---:|---:|
| Vector-only | 1.00 | 0.88 | 14.50s |
| Hybrid BM25 + RRF | 0.97 | 0.87 | 16.03s |

Run the full evaluation against an already-indexed repository:

```powershell
docker compose run --rm api python -m app.evals ../evals/golden.yaml `
  --source-url https://github.com/fastapi/fastapi.git `
  --results-dir ../evals/results
```

CI runs Ruff, an enforced targeted mypy check (`mypy>=1.13,<1.20`), all backend tests, deterministic objective evaluation tests, and the frontend type check/build on every push or pull request. The separate `eval-live` job is manual (`workflow_dispatch`) and requires `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` repository secrets; it runs the real FastAPI ingestion and golden-set evaluation and is never silently skipped.

The frontend uses Next.js 15.5.22 on the compatible 15.x line. The verified production-only
audit result after the dependency update is `0 vulnerabilities`.

## Observability

OpenTelemetry spans are emitted for ingestion, retrieval, LLM, and MCP operations through the console exporter. Anthropic calls are instrumented with Langfuse when `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` are configured.

Secrets are loaded from `.env`, which is gitignored. Never commit `.env` or API keys.

For submission, create the archive from committed files only:

```powershell
make submission
tar -tf submission.zip | Select-String '(^|/)\.env$'
```

The second command must return no matches. If credentials were ever exposed, revoke
and regenerate them at Anthropic, OpenAI, and Langfuse before submitting.

## Verified evidence

The application was browser-verified against the real FastAPI index:

![Chat answer with citations](screenshots-chat-citation.png)

![Repository map](screenshots-repo-map.png)

![Citation source viewer](screenshots-source-viewer.png)

The complete recording plan is in [DEMO_VIDEO_SCRIPT.md](DEMO_VIDEO_SCRIPT.md). It covers
ingestion, health checks, repository browsing, exact source ranges, streaming citations,
conversation memory, refusal behavior, MCP, CI/evaluation, and observability. The video itself
is not committed to the repository.

A previous fresh Compose validation applied the then-current SQL migrations, passed 46 backend tests, and returned successful `/health` and `/health/db` responses. New verification results are recorded only after the current environment completes the checks below.

## Engineering decisions

The running decision log is in [DECISIONS.md](DECISIONS.md), and measurements are in [FACTS.md](FACTS.md). The most consequential choices were:

- Claude Sonnet is the default LLM and `text-embedding-3-small` is the default embedding model.
- Postgres + pgvector stores both metadata and vectors.
- Context is capped at 6,000 tokens and chunks are never truncated mid-range.
- Vector-only retrieval shipped because the hybrid experiment did not improve the measured gates.
- Every vector query is filtered by `repo_id`; HNSW filtering can reduce approximate-search recall at larger scale, so I would benchmark partitioning or per-repository indexes before changing it.
- Conversation memory is intentionally simple: the last 10 messages.

## Productionising and deployment

For a production deployment, I would move Postgres and pgvector to a managed PostgreSQL service, store API keys in the cloud secret manager, and add authentication, authorization, tenant isolation, and rate limits before exposing ingestion or chat publicly. Repository ingestion would run in background workers behind a queue with size, time, network-egress, and repository-policy limits. Large source files and generated artifacts could use object storage with lifecycle retention, while the API would remain stateless and scale horizontally behind a load balancer. Managed OpenTelemetry/Langfuse-compatible observability, encrypted backups, point-in-time recovery, CI/CD promotion checks, dependency scanning, and private-source redaction/retention controls would complete the deployment baseline.

## What I would do differently with more time

I would add multi-language parsing incrementally, move ingestion to cancellable asynchronous jobs, expand the golden set with measured failure categories, and test reranking only if retrieval experiments justify it. I would also add repository access control, load testing, and explicit conversation/turn status for partial streaming failures.

## Engineering standards

I followed containerized local setup, typed HTTP boundaries, async database and embedding I/O, migration-based schema changes, deterministic tests, focused evaluation gates, repository-scoped data access, secret exclusion, and CI validation for both backend and frontend. I deliberately skipped authentication, multi-tenancy, rate limiting, arbitrary public ingestion APIs, broad language support, call-graph analysis, agent loops, and reranking without measured benefit because they are outside this take-home's core scope.

## Deliberate non-goals

The following are intentionally not implemented: authentication, user accounts, multi-tenancy, rate limiting, multi-repository search, incremental git-pull indexing, multi-language parsing, call-graph analysis, architecture/dependency graphs, agentic retrieval loops, cross-encoder reranking, load testing, and migrations tooling beyond the committed SQL migrations.

These omissions keep the submission focused on the core value: correct, clickable, verifiable code citations.

## AI-assisted development notes

Development was checkpointed by phase with focused tests. Specific rework included:

- A CRLF citation corruption bug was found by the line-range fidelity test and fixed by switching source reads to bytes.
- Test fixtures were found to delete every repository's chunks; the deletes were scoped through the repository cascade.
- The initial refusal question was answerable in the negative, so it was replaced with a genuinely unanswerable question and the refusal gate reached 1.00.
- BM25 + RRF was implemented, measured, and rejected based on evaluation results rather than retained for keyword coverage.

## Project status

The implementation is pushed to `main`. The local Langfuse trace has been verified through the authenticated API, and the remaining handoff step is to submit the assignment through the Newpage submission link after confirming the GitHub Actions run.
