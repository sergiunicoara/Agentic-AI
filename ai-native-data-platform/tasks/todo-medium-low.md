# Fix plan — Medium/Low findings — 2026-09-25

Continuation of the follow-up audit (see tasks/todo.md for the Critical/High
pass this builds on). Scope: the Medium + Low findings that pass explicitly
deferred. Same verification standard: real Postgres 16 + pgvector for
anything SQL-shaped, the real FastAPI app via TestClient for anything
request-shaped, mocked unit suite otherwise.

## Medium

- [x] M1 — `X-Experiment` header lets a client pick any retrieval pipeline
      directly, bypassing A/B assignment; `factory._load_experiment_config`
      will load any `.yaml`/`.yml` file path handed to it (path traversal
      into arbitrary YAML on the server's filesystem); each distinct header
      value permanently occupies a slot in `build_pipeline`'s `lru_cache`.
- [x] M2 — Shard "hedging" (`_hedged_retrieve`) waits for *both* the primary
      and the hedge request (`t1.join(); t2.join()`) — this doubles load
      and does nothing for tail latency, the opposite of what hedging is
      for.
- [x] M3 — Ingestion job leases have no ownership check on completion:
      `mark_success`/`mark_failure` update by `id` alone, not
      `WHERE locked_by = :worker_id`, so a worker whose lease already
      expired (and was already reclaimed by another worker) can still
      "successfully" complete a job a different worker is now running,
      clobbering its outcome.
- [x] M4 — A retrieval result curtailed by the latency budget (fewer stages
      run, or the reranker skipped) is cached identically to a complete
      result, under the same key, for the full TTL.
- [x] M5 — OpenSearch client: `verify_certs=False` unconditionally, no
      auth support, hand-rolled `http://`/`https://` URL parsing.
- [x] M6 — NL→SQL: raw DB exception text returned to the client in the
      500 response (`f"Query execution failed: {error}"`); a validation
      rejection is audit-logged with `error=None` instead of the reason.
- [x] M7 — Prompt-injection/safety regexes misfire in both directions:
      "ignore **the** previous instructions" bypasses the
      `instruction_override` pattern (only matches "ignore previous
      instructions" / "ignore all previous instructions"); ordinary
      questions like "what's your system prompt setup for the bot" or
      "can you act as a reviewer" get blocked as attacks; a 13-19 digit
      sequence (e.g. an order number) gets redacted as a credit card.
- [x] M8 — MMR reranker: `WHERE id::text = ANY(:ids)` prevents primary-key
      index use on `document_chunk.id`; the embedding-cache dicts
      (`_EMB_CACHE`) are module-level and mutated with no lock, unsafe
      under FastAPI's threadpool-executed sync routes.
- [x] M9 — `ivfflat` indexes are created with zero rows in the table
      (`scripts/init_db.sql` runs before any data exists) and
      `ivfflat.probes` is never set, so the default (1) is used — real
      recall will be poor once data exists, silently.

## Low / hygiene

- [x] L1 — `Makefile`'s `db-bootstrap`/`db-seed` targets call
      `scripts/bootstrap_db.py` / `scripts/seed_eval_data.py`, neither of
      which exists.
- [x] L2 — `ops/sql/001_workspace_index_state.sql` declares
      `workspace_id uuid`, conflicting with the real (TEXT) schema in
      `scripts/init_db.sql` — currently inert only because
      `CREATE TABLE IF NOT EXISTS` silently no-ops when init_db.sql runs
      first.
- [x] L3 — Dockerfile bakes `.env.example` into the image as `.env` and
      runs as root.
- [x] L4 — `requirements.txt` is entirely unpinned; `pydantic-ai[openai]`
      warns the `openai` extra doesn't exist on the installed version.
- [x] L5 — `app/eval/experiments/hybrid_rrf.yaml` and `baseline.yaml`
      build the identical pipeline (both default to `retrieval_mode`,
      neither sets `mode:`) despite the experiment's name/purpose.
- [x] L6 — `InMemoryLRU` (`app/core/cache.py`) mutates its `OrderedDict`
      with no lock; unsafe under FastAPI's threadpool-executed sync routes,
      same class of bug as M8.
- [x] L7 — `/health` reports OK regardless of whether Postgres/Redis/
      OpenSearch are actually reachable.
- [x] L8 — `'gen_err' in locals()` in `/ask` — fragile way to ask "did we
      reach the generation branch".
- [x] L9 — `graphify-out/` (a 2.5MB generated cache directory) is
      committed to the repo.

## Verification

- [x] Real Postgres 16 + pgvector instance for anything SQL-shaped.
- [x] Real FastAPI app (TestClient) for anything request-shaped.
- [x] Mocked unit suite (`pytest tests/`) stays green throughout (255
      passed, 1 skipped).

## Review

All 18 Medium/Low findings from the follow-up audit are fixed, verified,
and committed on `claude/gallant-knuth-ypmu42` (13 commits on top of the
Critical/High pass: `cc7e7b6` .. `e4e1903`).

**Security-relevant fixes (M1, M5, M6, M7):**
- M1: `X-Experiment` override now requires `ALLOW_EXPERIMENT_OVERRIDE=true`
  *and* a valid admin token (same gate already used for embedding-model
  override); `_load_experiment_config` rejects any name that isn't a bare
  basename via `os.path.basename` round-trip before touching the
  filesystem, closing the path-traversal opening.
- M5: OpenSearch client now parses the URL with `urllib.parse.urlsplit`
  (correct handling of embedded credentials/ports), forwards HTTP basic
  auth when the URL carries credentials, and `verify_certs` is a real
  setting (`opensearch_verify_certs`, default `True`) instead of a
  hardcoded `False`.
- M6: `run_nl_query` no longer leaks raw exception text (table/column
  names, SQL fragments, driver error strings) to the HTTP client — 500s
  return a generic message while the full detail still lands in the audit
  log and an `nl_query_execution_failed` event for operators. A validation
  rejection now correctly populates the audit log's `error` column instead
  of silently logging `None`.
- M7: `prompt_guard.py` and `output_moderation.py` regexes retuned in both
  directions — closed real false negatives (filler-word instruction
  overrides), removed false positives that were blocking ordinary
  questions ("what system prompt format does OpenAI use", "act as a
  reviewer"), and added a Luhn checksum gate so order/invoice numbers stop
  being redacted as credit cards. One existing parametrized test case was
  corrected (a query that's still blocked, just now taxonomized as
  `jailbreak` instead of `role_hijack`, which is the more accurate code —
  "DAN" is a real jailbreak trigger).

**Correctness fixes (M2, M3, M4, M8, M9, L2):**
- M2: `_hedged_retrieve` rewritten to a real bounded-wait fan-out — both
  shard requests start concurrently and the call returns as soon as either
  finishes or the latency budget expires, instead of always waiting for
  both (which was strictly worse than not hedging at all).
- M3: `mark_success`/`mark_failure` now fence on the job's `attempts`
  counter (`WHERE id = ... AND attempts = :attempts`), detect a 0-row
  update (lease already reclaimed by another worker) and emit
  `ingestion_job_stale_completion` instead of silently clobbering another
  worker's outcome.
- M4: retrieval results produced under a curtailed budget (reranker
  skipped, stages cut short) are flagged `degraded=True` and are no longer
  written to the shared cache, so a later full-budget request can't be
  served a truncated result from cache.
- M8: reranker embedding-ID lookups switched to
  `id = ANY(CAST(:ids AS uuid[]))` (index-eligible) from
  `id::text = ANY(:ids)`; the module-level embedding cache gained a
  `threading.Lock`, matching the same fix already needed for L6.
- M9: pgvector indexes switched from `ivfflat` (needs representative data
  present *before* index creation to get good cluster centroids, which
  `init_db.sql` can never provide) to `hnsw`, which builds incrementally
  and has no such ordering requirement.
- L2: `ops/sql/001_workspace_index_state.sql`'s `workspace_id` column
  changed from `uuid` to `text`, matching the real schema in
  `scripts/init_db.sql` it was silently conflicting with.

**Hygiene / operability fixes (L1, L3, L4, L5, L6, L7, L8, L9):**
- L1: `Makefile` targets now call scripts that actually exist
  (`scripts/init_db.sql` via psql, `scripts/seed_eval_corpus.py`), with
  `ADMIN_DATABASE_URL`/`DATABASE_URL` defaults matching the RLS-aware
  bootstrap from the Critical/High pass.
- L3: Dockerfile no longer bakes `.env.example` into the image as `.env`;
  image now runs as an unprivileged `app` user.
- L4: every line in `requirements.txt` pinned to an exact version
  extracted from a real, fully-successful `pip install` (verified both in
  a scratch venv and inside an actual `docker build`); dropped the
  nonexistent `pydantic-ai[openai]` extra.
- L5: `hybrid_rrf.yaml` now explicitly sets `mode: hybrid`, `fusion: rrf`,
  `rerank: mmr` so it's actually distinct from `baseline.yaml` instead of
  both silently resolving to the same default pipeline.
- L6: `InMemoryLRU` gained a `threading.Lock` around `get`/`set`.
- L7: added a real `/health/ready` readiness endpoint that checks Postgres
  (via `SELECT 1`) and reports Redis/OpenSearch status; `/health` stays a
  cheap liveness check and the k8s readiness probe now points at
  `/health/ready` (liveness probe correctly stays on `/health` — an
  external dependency outage should not restart the pod).
- L8: `/ask`'s generation-error tracking replaced `'gen_err' in locals()`
  with an explicit `gen_err: str | None = None` declared up front.
- L9: `graphify-out/` (117 files, 2.5MB of generated output containing the
  author's local Windows paths) removed from git entirely; added
  `.gitignore` covering it and other generated/artifact directories
  (`artifacts/`, `data/index_manifests/`, `runs/`, `reports/`,
  `__pycache__/`, `.env`).

**Verification standard held throughout:** every SQL-shaped fix (M1's path
check aside) was proven against a real Postgres 16 + pgvector instance —
including `EXPLAIN (ANALYZE, BUFFERS)` for M8's index-eligibility claim,
row-fencing races reproduced for M3, and end-to-end `/ask` and `/ingest`
requests through `TestClient` for M1, M4, M6, M7. Concurrency fixes (M8,
L6) were reproduced racing before the fix and proven race-free after via
`sys.setswitchinterval()`. New regression tests were added for every item
where the mocked suite could meaningfully pin the behavior
(`tests/test_experiment_factory.py`, `tests/test_hedged_retrieve.py`,
`tests/test_ingestion_job_fencing.py`, `tests/test_reranker_cache_concurrency.py`,
`tests/test_opensearch.py::TestMakeClientURLParsing`,
`tests/test_nl_query_service.py`, extended `tests/test_safety.py`,
`tests/test_cache_concurrency.py`, `tests/test_reliability.py`). Full
mocked suite: 255 passed, 1 skipped.

**Deliberately not touched (out of scope for this pass):**
- `app/vectorstore/pgvector_scaling.py` already supports both
  `ivfflat`/`hnsw` as a configurable choice — M9 only needed to change
  which one `init_db.sql` uses by default.
- `build-essential`/`libpq-dev` left in the Dockerfile's apt-get list
  despite likely being unnecessary once `psycopg2-binary` (which ships
  its own libpq) is installed — untested without a from-scratch build and
  outside L3/L4's stated scope.
- `k8s/eval-job.yaml`/`k8s/cronjob-drift.yaml` still carry the same
  `NetworkPolicy` label-selector gap fixed for the main deployments in the
  Critical/High pass (H6) — noted there as a separate, unfixed gap; not
  revisited in this pass since no new Medium/Low finding named it.
