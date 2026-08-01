# Decisions log

- **LLM**: Claude Sonnet, model string config-driven via `LLM_MODEL` env var. Matches JD's
  explicit naming of Claude Code / Claude Agent SDK / MCP.
- **Embeddings**: OpenAI `text-embedding-3-small`, 1536-dim. Cheap, fast, well-documented,
  easy to swap later since `EMBEDDING_MODEL`/`EMBEDDING_DIM` are both config values.
- **DB**: single Postgres 16 + pgvector instance for both vectors and metadata (repos/files/
  chunks/messages) — avoids running a separate vector DB for a dataset this size.
- **Frontend**: Next.js App Router + TS + Tailwind, not Streamlit/Gradio — role is Fullstack,
  and SSE streaming + a real citation-click-to-source-panel UX needs a real frontend.
- **Phase 1 scope**: skeleton only (Docker Compose, pgvector migration, health checks, empty
  CI). Ingestion/retrieval/chat/evals/frontend UI are later phases per the spec's own
  checkpoint discipline.
- **Ingestion CLI naming**: entrypoint is `python -m app.ingest`, not `python -m codex.ingest`
  as literally shown in the spec — this repo's package is `app` (set in Phase 1), so `codex`
  would require renaming everything. Functionally identical, just a different module path.
- **`.gitignore` respect**: reused git itself (`git ls-files --cached --others
  --exclude-standard`) instead of reimplementing gitignore semantics. Non-git local
  directories fall back to `pathspec`'s `GitIgnoreSpec` against a root `.gitignore` plus a
  fixed default-ignore list (`.git/`, `__pycache__/`, `.venv/`, `node_modules/`, `dist/`,
  `build/`). Avoids maintaining a second gitignore parser.
- **Chunk token ceiling**: 800 tokens (`tiktoken` `cl100k_base`), not specified in the spec —
  chosen to leave headroom for the prepended context header before hitting typical embedding
  model input limits. Over-ceiling chunks split on line boundaries only, never mid-line.
- **Class chunking**: a class's own chunk covers only its "preamble" (docstring, class-level
  attributes, the `class Foo(Base):` line) — not the full class body. This mirrors the
  module-preamble rule and guarantees class and method chunks never overlap in line range.
  Spec's literal wording ("one chunk per...class, and method") is ambiguous on this point;
  chose the non-overlapping interpretation over a naive full-span class chunk that would
  duplicate every method's content in two different chunks.
- **Markdown chunking**: sections are flat, non-nested slices (each line belongs to exactly
  one section, ending at the next heading of any level) — `symbol_path` still carries the
  full breadcrumb (e.g. `Setup > Installation`) so hierarchy isn't lost, but content isn't
  duplicated between a parent section and its subsections.
- **`content_hash` caching**: implemented as run-level caching only (skip re-embedding a file
  whose hash matches what's already stored) — not cross-commit incremental re-indexing, which
  stays an explicit spec non-goal.
- **Newline handling bug (caught by tests, not written correctly the first time)**:
  `Path.read_text()` silently applies universal-newline translation (`\r\n` → `\n`), which
  would corrupt exact citation line-ranges for any CRLF-authored file. Fixed by reading
  `read_bytes().decode(...)` everywhere content gets line-sliced, preserving the file's actual
  bytes. Caught by the mandatory line-range fidelity test — first real proof that test was
  worth writing.
- **Testability without API keys**: `Embedder` is a `Protocol`; a deterministic `FakeEmbedder`
  (SHA-256-seeded fixed-dim vectors) backs all tests and a `--fake-embeddings` CLI flag for dry
  runs, so CI and local iteration never need a real `OPENAI_API_KEY`.
- **Phase 3 scope: no real Anthropic API calls.** `LLMClient` is a `Protocol` mirroring
  `Embedder`; a deterministic `FakeLLMClient` backs all automated tests and the manual smoke
  test. A real end-to-end run with the actual model is deferred to Phase 5 (UI) / Phase 4
  (evals), where there's a reason to spend real tokens on verification.
- **Table definitions consolidated** from `app/ingest/tables.py` into a shared `app/tables.py`
  (single `MetaData`) once retrieval needed the `messages` table too — avoids two `Table`
  objects for the same Postgres table under different `MetaData` instances, which SQLAlchemy
  would treat as a conflict.
- **Context budget**: 6,000 tokens (`cl100k_base`), chunks included whole in rank order, never
  truncated mid-chunk — a partial chunk would break citation-line-range fidelity. `top_k=8`
  retrieved candidates gives the budget-fill logic real headroom to choose from.
- **Citation format**: `[path/to/file:start-end]`, enforced via the system prompt and parsed
  from the completed answer. This is the historical Phase 3 decision; the current service
  validates citations against retrieved chunks before finalizing the answer and exposes only
  those validated citations as clickable UI controls.
- **Conversation memory**: last 10 messages per `(repo_id, conversation_id)`, loaded before each turn and
  mapped straight to Anthropic's `messages` param — "simple," per spec, not a summarization or
  sliding-window scheme.
- **Token-counting deduplication**: extracted the `tiktoken`-based counter out of
  `app/ingest/chunker.py` (Phase 2) into a shared `app/tokens.py` once `context.py` needed the
  same logic — avoided a second private `_count_tokens` copy.
- **CI/format lesson from Phase 2 repeated correctly this time**: `ruff format` run inside a
  running container only touches paths that are actually volume-mounted (`app/`, not `tests/`
  or root files) — Phase 2's CI failure came from trusting an in-container reformat that never
  reached the host. This phase's fix used a one-off `docker run` with the *entire* `backend/`
  directory bind-mounted, then reverified `ruff check`/`pytest` against a freshly rebuilt image
  before committing — not just an in-place edit.
- **Phase 4 requires real API calls** — unlike Phases 1-3, `retrieval_hit@5` needs semantically
  meaningful embeddings and `citation_precision`/`groundedness` need a real generated answer to
  judge; fakes cannot produce meaningful numbers here. Ran real OpenAI + Claude calls for both
  the demo-repo golden set and the CI fixture gate, per user decision.
- **Evaluation workflow**: the full 30-question set (`evals/golden.yaml`) runs against the real
  demo repo (`fastapi/fastapi`, `fastapi/` package dir) manually with credentials. Current CI
  runs deterministic metric and judge tests without API secrets; it does not claim to run a
  smaller fixture evaluation.
- **`fastapi/fastapi` subdir-scoped ingestion**: extended `walker.walk()`/`resolve_source()`
  with a `subdir` param (`--subdir fastapi` on the CLI) that uses `git ls-files -- <subdir>` so
  `.gitignore` still resolves correctly from the real repo root, rather than naively walking a
  subdirectory in isolation.
- **Golden-set verification against ground truth**: before running the real eval, cloned
  `fastapi/fastapi` separately and grepped every `expected_files`/`expected_symbols` entry in
  `golden.yaml` against the actual checkout — 3 symbols (`WebSocket`, `CORSMiddleware`,
  `run_in_threadpool`) are Starlette re-exports rather than local definitions, present as text
  in the module but not as `class`/`def` lines. Confirmed the substring-based citation check
  still matches on chunk `content`, so no golden-set changes were needed.
- **BM25 + RRF decision, per spec's own required experiment**: ran the full golden set both
  vector-only and hybrid (Postgres full-text search + vector, fused via Reciprocal Rank Fusion,
  k=60). Vector-only won on every gated metric (retrieval_hit@5 1.00 vs 0.97, citation_precision
  0.88 vs 0.87) and was faster (14.5s vs 16.0s p95 latency — hybrid pays for two DB round-trips
  plus fusion per question). Kept vector-only as the default; `search_chunks_hybrid()` stays in
  the codebase (documented, tested) but isn't wired into the default retrieval path. Both number
  sets are in `FACTS.md` — a measurement-backed decision, not a resume-keyword one, per spec's
  own framing.
- **BM25 computed inline**, no stored `tsvector` column or GIN index — `to_tsvector('english',
  chunks.content)` computed per-query. Fine at 581 chunks; would add a generated column + index
  before scaling to a much larger corpus.
- **Refusal gate failure left honest, not gamed**: one of three refusal questions
  ("How does FastAPI implement its own built-in database ORM?") got a real, grounded,
  substantive answer ("no — it recommends SQLModel instead," cited from the actual skill docs)
  that the refusal judge correctly did NOT classify as a refusal, since it isn't one — it's a
  correct negative answer backed by context. This is a golden-set question design gap (the
  question turned out to be answerable in the negative, unlike the other two which are
  genuinely absent from the indexed content), not a retrieval/generation defect. Documented in
  `FACTS.md` rather than reworded to force a pass — an honest 0.67 refusal_accuracy with a real
  explanation is worth more than a cosmetically perfect gate.
- **CI eval gate needs repo secrets I cannot set myself** — no `gh` CLI or repo-admin access in
  this environment. `eval-fixture` job checks for `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` and
  reports "skipped" rather than failing when they're absent; the user needs to add both as
  GitHub Actions repo secrets (Settings > Secrets and variables > Actions) for the gate to
  actually run.
- **`files.content` column added** (migration `002_add_file_content.sql`) so `/file` serves
  exact raw source straight from Postgres — chunks alone don't fully tile every file
  (module-preamble only covers lines before the first top-level def), so reconstructing raw
  content purely from chunks would have gaps for files with module-level code after/between
  top-level defs. Required re-ingesting `fastapi/fastapi` and `sample_repo` (both already
  ingested without it).
- **Ingestion stays CLI-only for Phase 5** — the UI lists already-ingested repos (`GET /repos`)
  rather than adding an in-UI ingest trigger. Matches spec's Phase 5 checklist exactly (chat +
  citation viewer + repo map, not an async ingest-job UI), and keeps the "one command" framing
  from spec §5 intact.
- **Repo map**: `app/browse/repo_map.py` groups a repo's chunks by file, nests `method` chunks
  under their parent `class` chunk by symbol_path prefix match, and nests files into a
  directory tree by splitting `path` on `/`. `module`-kind (preamble) chunks are excluded — not
  a distinct browsable symbol. Markdown `markdown_section` entries stay flat (no nesting),
  matching the chunker's own flat-section design from Phase 2.
- **SSE parsed manually over `fetch()`+`ReadableStream`** in the frontend, not `EventSource` —
  `/chat` is a POST endpoint (needs a JSON body for `repo_id`/`conversation_id`/`message`), and
  `EventSource` only supports GET.
- **CORS**: `CORSMiddleware` added to `main.py`, allowing only `WEB_ORIGIN` (default
  `http://localhost:3000`) — the browser calls the API directly (client-side fetch), not via
  Next.js SSR, so the API needs to allow that origin explicitly.
- **`NEXT_PUBLIC_API_URL` is a Docker build ARG**, not a runtime env var — Next.js inlines
  `NEXT_PUBLIC_*` vars into the client bundle at build time, so it has to be passed via
  `docker-compose.yml`'s `build.args`, not `env_file` (which only affects the running
  container, too late for a value already baked into the JS bundle).
- **Found and fixed a real test-isolation bug**: 7 test files' `_clean_db` autouse fixtures did
  `delete(chunks_table)` / `delete(files_table)` with **no WHERE clause** — wiping every repo's
  ingested data on every test run, not just the test's own. Only the `repos` delete was scoped
  by `source_url`. This silently destroyed the real `fastapi/fastapi`/`sample_repo` ingestion
  data (from Phase 4) every time `pytest` ran during Phase 5 development — caught when
  `/repo-map` returned an empty tree for a repo that should have had 581 chunks. Fixed by
  relying on the existing FK `ON DELETE CASCADE` chain (`repos → files → chunks`) and only
  ever deleting scoped `repos` rows; removed the blanket deletes entirely rather than trying to
  scope them by file_id. `messages` deletes remain a test-isolation cleanup across the test
  database; production history is repository-scoped and protected by the migration 004 foreign
  key.
- **Refusal golden-set correction**: replaced q30's database-ORM question with a proprietary GPU-scheduler question. The former was answerable in the negative from indexed FastAPI guidance, so it was not a valid refusal case; the corrected question is outside the indexed codebase.
- **MCP transport**: used FastMCP over stdio, launched by the committed `.mcp.json` through Docker Compose. This keeps Claude Code and the HTTP API on the same retrieval/browse modules without adding another network service.
- **Phase 6 observability**: added OTel spans with the console exporter around ingest, chat retrieval/LLM, and MCP calls. Langfuse `observe` hooks the Anthropic methods and remains credential-gated through `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`; no cloud trace was captured locally because those credentials are empty.
- **Langfuse export hardening**: the real eval showed unauthorised Langfuse export attempts when credentials were empty. The decorator is now a no-op unless both Langfuse keys are configured, so local runs do not emit misleading failed exports; valid keys are still sufficient to enable the trace.
- **Langfuse verification**: after normalizing quoted `.env` values, a real streamed chat request completed with HTTP 200 and the authenticated Langfuse traces endpoint returned HTTP 200 with one trace.
- **Phase 7 clean-install check**: CI applies all four committed SQL migrations. The later migrations add vector/integrity indexes and repository-scoped conversation history, so fresh CI and Compose databases receive the same schema.
- **Demo selection**: the UI prefers the indexed FastAPI demo repo on first load, falling back to the newest indexed repo when the demo is absent. This keeps test fixtures from becoming the reviewer-facing default without restricting which repositories can be indexed.

## Final hardening decisions

- **Progressive SSE**: Claude deltas are yielded immediately. The `done` event carries the
  validated citations and `final_text`; the frontend replaces provisional content with that
  accepted text so uncited factual answers can still be safely replaced after generation.
- **Repository-scoped history**: migration 004 deletes legacy messages with no `repo_id`
  because they cannot be safely associated with a repository, then enforces the foreign key,
  `NOT NULL`, and `(repo_id, conversation_id, created_at DESC)` index.
- **Frontend security maintenance**: Next.js remains on the compatible 15.x line at 15.5.22.
  npm overrides pin vulnerable transitive PostCSS and Sharp packages to patched versions.
- **Mypy reproducibility**: the development dependency is constrained to `>=1.13,<1.20`.
  The verified 1.19.1 release passes the targeted check, while newer releases produced an
  internal error in this environment.
