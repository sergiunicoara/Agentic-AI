# Facts log (raw measurements only)

## Phase 6 - MCP + observability
- MCP tools: 3
- New backend tests: 1
- Backend tests passed: 46
- Ruff violations: 0
- Docker API image builds: 1
- Langfuse credentials configured locally: 1
- Langfuse traces captured locally: 1
- Full golden-set questions: 30
- Full golden-set retrieval_hit@5: 1.00
- Full golden-set citation_precision: 0.85
- Full golden-set groundedness: 0.99
- Full golden-set refusal_accuracy: 1.00
- Full golden-set p95 latency seconds: 14.29

## Phase 7 - hardening
- CI migration files applied: 4 (historical static-workflow note; superseded by the final
  hardening verification below)
- Fresh Compose project test count passed: 46
- Fresh Compose API health checks passed: 2
- Fresh Compose validation elapsed seconds: 48

## Phase 2 — ingestion (fixture repo: backend/tests/fixtures/sample_repo)
- Files ingested: 4 (3 .py, 1 .md)
- Chunks produced: 17
  - pkg/__init__.py: 1 chunk
  - pkg/models.py: 5 chunks (1 module preamble, 1 class, 2 methods, 1 function)
  - pkg/utils.py: 6 chunks (1 module preamble, 5 from token-ceiling split of one function)
  - README.md: 5 chunks (markdown sections)
- Token ceiling: 800 tokens (cl100k_base) — pkg/utils.py's long_running_pipeline (269 lines,
  ~1050 lines total incl. docstring) split into 5 sub-chunks, each ≤ 800 tokens, contiguous
  line ranges (4-60, 61-117, 118-174, 175-231, 232-268).
- Ingest elapsed time (FakeEmbedder, no network): 0.23s for full run, 0.14s for cached re-run
  (all 4 files skipped via content_hash match).
- Backend test count: 11 (test_health: 1; ingest: walker 2, parser 2, chunker 4, store 2).
- Embedding model (config default): OpenAI text-embedding-3-small, 1536-dim.

## Phase 3 — retrieval + chat (fixture repo, FakeEmbedder + FakeLLMClient)
- Backend test count: 23 total (+12 from Phase 3: search 2, context 3, citations 4, service 2,
  chat endpoint 1).
- Context budget: 6,000 tokens (cl100k_base); top_k=8 candidates retrieved per query.
- Manual smoke test (service.py direct call, fixture repo): question "What does create_user
  do?" → correctly cited [pkg/models.py:18-20], matching the actual function's line range
  from Phase 2 ingestion. Two-turn conversation memory verified — second turn's LLM call
  included the first turn's user question and assistant answer in history.
- LLM model (config default): Claude Sonnet, model string from LLM_MODEL env var — not
  exercised with a real API call in this phase (see DECISIONS.md).

## Phase 4 — evals (real run: fastapi/fastapi, `fastapi/` package dir, real OpenAI + Claude)
- Ingestion: 55 files (48 .py, 7 .md under `.agents/skills/`), 581 chunks, 25.07s elapsed.
- Backend test count: 40 total (+17 from Phase 4: metrics 8, judge 5, walker subdir 2, hybrid 2).
- Golden set: 30 questions (27 informational + 3 refusal) in `evals/golden.yaml`, hand-written
  and verified against the actual clone (every expected_file/expected_symbol confirmed present
  before running) — 3 symbols (`WebSocket`, `CORSMiddleware`, `run_in_threadpool`) turned out to
  be re-exports from Starlette rather than definitions in FastAPI's own files, present as text
  but not as `class`/`def` — citation_precision's substring check still matches on `content`.

**Vector-only (baseline):**
| Metric | Value | Gate |
|---|---|---|
| retrieval_hit@5 | 1.00 | >= 0.80 ✅ |
| citation_precision | 0.88 | >= 0.85 ✅ |
| groundedness | 1.00 | >= 0.70 ✅ |
| refusal_accuracy | 0.67 | == 1.00 ❌ |
| p95_latency | 14.50s | report only |

**Hybrid (BM25 full-text + vector, RRF k=60):**
| Metric | Value | Gate |
|---|---|---|
| retrieval_hit@5 | 0.97 | >= 0.80 ✅ |
| citation_precision | 0.87 | >= 0.85 ✅ |
| groundedness | 1.00 | >= 0.70 ✅ |
| refusal_accuracy | 0.67 | == 1.00 ❌ |
| p95_latency | 16.03s | report only |

**Decision: vector-only wins** — matches or beats hybrid on every gated metric (retrieval_hit@5
1.00 vs 0.97, citation_precision 0.88 vs 0.87) and is faster (14.5s vs 16.0s p95, hybrid pays
for two DB queries + fusion per question). Kept as the default; hybrid code stays in
`app/retrieval/search.py` (`search_chunks_hybrid`) but isn't wired into the default path.

**Refusal gate failure, examined honestly**: q30 ("How does FastAPI implement its own built-in
database ORM?") was answered correctly and grounded — the model said "no, FastAPI doesn't have
one; it recommends SQLModel" citing the real skill docs — but the refusal judge scored this as
"not a refusal" since it's a substantive, informative answer rather than a hedge. This is a
golden-set question design gap (the question is actually answerable in the negative, unlike
q29/q31 which are genuinely absent from the indexed content), not a retrieval or generation
bug. Left the number honest rather than reworking the question to force a pass.

## Phase 5 — frontend (chat + citation viewer + repo map)
- Backend test count: 45 total (+5 from Phase 5: browse repo_map 3, browse file_content 2). This is historical; current verification must be rerun after later hardening changes.
- Re-ingested `fastapi/fastapi` (55 files, 581 chunks) and `sample_repo` (4 files, 17 chunks)
  with `files.content` populated for the new `/file` endpoint.
- Browser-verified full UX flow against real data (real OpenAI embeddings + real Claude):
  - Repo map: `fastapi/routing.py` correctly nests `add_task` under `BackgroundTasks` (class)
    in `fastapi/background.py`; clicking a symbol opened the source viewer at the exact chunk
    range (`fastapi/background.py:11-39`), content byte-identical to the ingested source.
  - Chat: "What does the include_router method do?" streamed a real answer citing 6 sources
    across `routing.py`, `applications.py`, and the SKILL.md docs; each citation rendered as a
    clickable chip.
  - Citation click → `/file?path=fastapi/routing.py` (200 OK), source viewer updated correctly.
  - Conversation memory: follow-up "give me a shorter summary of what you just explained"
    correctly condensed the same `include_router` answer — confirms history is passed through.
- Test-isolation bug found and fixed during this phase (see DECISIONS.md): 7 test files were
  blanket-deleting `files`/`chunks` on every run, silently wiping real ingested data.

## Final hardening verification â€” 2026-07-31

- The Python 3.12 container run completed `58 passed` backend tests, including progressive
  SSE, refusal, invalid-citation, repository-history, parser, and chunker coverage.
- `ruff check .` passed on the backend, and the enforced targeted mypy command passed with no issues.
- `npm audit --omit=dev` reported `0 vulnerabilities` after upgrading Next.js to 15.5.22
  and pinning patched transitive PostCSS 8.5.25 and Sharp 0.35.3.
- `npm ci`, `npx tsc --noEmit`, and `npm run build` passed after the dependency update.
- The development dependency now constrains mypy to `>=1.13,<1.20`; pip resolved 1.19.1 and
  the targeted command passed. Newer mypy releases produced an internal error in this project,
  so the upper bound keeps the CI gate reproducible.
- Migration 004 was verified both on an upgraded database (9 legacy unscoped messages removed,
  then `repo_id` became `NOT NULL`) and on a fresh schema after migrations 001 through 004.
- Commands run for this verification included `pytest -q`, `ruff check .`, the targeted
  `mypy` command, `npm ci`, `npm audit --omit=dev`, `npx tsc --noEmit`, `npm run build`, and
  direct backend/frontend Docker builds. The local health endpoints returned HTTP 200.
- The complete 30-question evaluation was not run in this pass; existing evaluation results
  remain historical and are not presented as validation of the newer evaluation metrics.
