# Audit fix plan — 2026-09-04

Source: 4-agent parallel audit (security, data integrity/concurrency, reliability/observability, test coverage).

## Batch A — SQL injection (Critical) — DONE
- [x] Whitelist `intent.aggregation` in `validator.py` against {COUNT,SUM,AVG,MIN,MAX} — closes the f-string injection into SELECT via `sql_builder.py:20-25`
- [x] Belt-and-suspenders: `sql_builder.py` raises if `aggregation` isn't one of the known set, regardless of validator

## Batch B — Security hardening (High) — DONE
- [x] Redact citation snippets before returning `/ask` response
- [x] ~~Wire `is_safe_context()` into `generation/service.py`~~ — already wired at `generation/service.py:25`; security audit's claim was a false positive, verified by reading the file directly
- [x] Add `/ingest/image` to the rate-limited route set in `api/main.py`
- [x] Add a request size cap on `/ingest/image` uploads (streamed, bounded read — not buffer-then-check)
- [x] Use `hmac.compare_digest` for the admin-token check in `api/main.py:203`

## Batch C — Remediation controller reversal (Medium-High) — DONE
- [x] Wire `clear_override()` into the controller loop — auto-clear once `violated` returns to 0 after having tripped; seeds `override_applied` from the real DB row on leader acquisition (handles handoff mid-remediation)
- [x] Remove dead/unused `start_remediation_loop()` in `remediation.py`
- [x] Leader lock liveness: re-verify the held connection is alive on each renew tick (`SELECT 1`) instead of trusting local state unconditionally; also fixed leadership-loss branch to actually call `release(lock)` (it previously just flipped a local flag)

## Batch D — Silent exception / observability gaps (Low-Medium) — DONE
- [x] `core/cache.py` (3 spots) — emit_event on Redis failure instead of bare `except: pass`
- [x] `retrieval/consistency.py` — distinguish probe failure from real epoch mismatch, emit_event
- [x] `core/exp/router.py` — emit_event when the override-read query fails
- [x] `indexing/index_state.py` — emit_event on swallowed exception

## Batch E — Reindex path critical bugs (Critical) — DONE
- [x] `indexing/lifecycle.py::reindex_embeddings()` — mutating `os.environ` has no effect on already-constructed `settings`; pass `embedding_version` explicitly to `run_manifest` instead. Also fixed a knock-on bug this uncovered: `old_active_version` was reading `stats["embedding_version"]`, which now correctly echoes the *target* version, so it needed to be captured from `get_index_state()` before the reindex starts
- [x] `indexing/pipeline.py` — fix `IndexingConfig` field name mismatch (`retry_backoff_ms` → `max_backoff_ms`, matching the call site and every external caller)
- [x] `indexing/pipeline.py::run_manifest` — add OpenSearch dual-write (bulk path previously never wrote to OpenSearch at all)
- [x] `indexing/pipeline.py` — call `bump_index_epoch()` after a successful `run_manifest` bulk backfill, not only at promote/cutover
- [x] `scripts/run_bulk_index.py` — missing `Path`/`time` imports

## Batch F — Ingestion pipeline correctness (High) — DONE
- [x] `ingestion/pipeline.py::process_document` — moved `embed_batch()` outside the write transaction (was holding a DB connection during N sequential embedding-provider round trips)
- [x] `ingestion/pipeline.py` — `chunk_hash` now used for real: `ON CONFLICT ... DO UPDATE ... WHERE chunk_hash IS DISTINCT FROM EXCLUDED.chunk_hash` — updates content in place on re-ingest with edited text, no-ops (as before) when unchanged, and keeps the row's stable id either way so OpenSearch never diverges
- [x] `ingestion/pipeline.py` / `opensearch/ingest.py::bulk_upsert` — surface partial-batch failures via a new `opensearch_dual_write_partial_failure` event (both the online and bulk dual-write paths)

## Batch H — Regression tests (closes the "fixed but untested" gap the audit found) — DONE
- [x] `tests/test_retrieval_pipeline.py` — cache hit returns `latency_ms == 0` even when stored payload has a non-zero value; `_cache_key` differs by `index_epoch`
- [x] `tests/test_index_state.py` — `bump_index_epoch` clears `_state_cache`/`_state_cache_expiry`; a `get_index_state` call after bump does not serve the stale epoch
- [x] `tests/test_validator.py` — malicious/unknown `aggregation` value rejected by both `validate_intent` and `build_sql` (defense in depth)
- [x] `tests/test_remediation_controller.py` — extracted the controller's hysteresis logic into a pure `evaluate_tick()` function (untestable before — it was inline in an infinite background-thread loop) and tested the hysteresis walkthrough, trip threshold, and auto-clear-on-recovery

## Batch I — Environment / docs — DONE
- [x] `dspy-ai` installs cleanly (`pip install dspy-ai`, v3.3.1) — `test_normalize.py` now collects; no `--ignore` needed
- [x] Corrected the stale "189/190 tests" figure to 213 in `README.md` and `docs/demo-script.md` (S08 dot-mockup, V.O., and the FADE OUT summary table)

## Verification — DONE
- [x] Full suite: `213 passed, 2 skipped in 8.75s`, 0 failures (the 2 skips are legitimate: opensearch-py not installed, no live OPENSEARCH_URL)

## Explicitly deferred (documented, not fixed — larger design decisions)
- Multi-replica in-process `index_state` cache TTL staleness (~10s window) — accepted eventual consistency, same tradeoff the online path already accepts
- Full Postgres↔OpenSearch reconciliation job for permanent dual-write divergence — flagged as a real gap, needs its own design, out of scope for this pass
- `delete_by_document()` dead code — no document-deletion feature exists at all; implementing one is a new feature, not a fix, flagging for a follow-up
- Hardcoded demo credentials in `docker-compose.yml` / `init_db.sql` seed — dev-only, intentional
- `enforce_tenancy` unused settings flag, provider settings (`embeddings_model`/`llm_model`/`vision_provider`) shadowed by raw `os.getenv` reads — real maintainability traps, but wiring `Settings` as the actual source of truth is a refactor across 3 provider modules, not a bug fix; flagging only
- `app/vectorstore/pgvector_scaling.py` — orphaned/uncalled; its f-string SQL identifier interpolation is only safe because nothing calls it with caller-supplied input today. Not wiring it up or deleting it without user direction on intent
- `dead code`: `pgvector_scaling.py` module — leaving in place, flagged

## Batch J — Closed follow-up gaps from architecture review — DONE
- [x] `app/vectorstore/pgvector_scaling.py` — deleted; confirmed zero references anywhere in the codebase (grep for `pgvector_scaling` returned nothing but the file itself)
- [x] `app/core/config.py` — `embeddings_model`/`llm_model` were never-read dead fields (pydantic-settings would've looked for `EMBEDDINGS_MODEL`/`LLM_MODEL`, but the real env vars are `OPENAI_EMBED_MODEL`/`OPENAI_CHAT_MODEL`). Renamed to match the real env vars exactly (`openai_embed_model`, `openai_chat_model`) plus added `embed_provider`, `llm_provider`, `openai_api_key`, `request_timeout_s` — no `.env`/`docker-compose.yml` changes needed since the env var names were already correct, just never wired to `Settings`
- [x] `app/providers/embeddings.py`, `app/providers/llm.py`, `app/providers/vision.py` — replaced raw `os.getenv(...)` module-level reads with `settings.*`, making `Settings` the actual single source of truth these three modules claimed to have
- [x] `app/retrieval/pipeline.py::RetrievalPipeline.run()` — `enforce_tenancy` existed on `Settings` but nothing ever read it (workspace scoping only worked because every caller happened to always pass a real `workspace_id`). Added an explicit guard: raises `ValueError` if `enforce_tenancy` is true and `workspace_id` is empty, instead of silently running an unscoped query
- [x] `tests/test_retrieval_pipeline.py` — added `TestEnforceTenancy` (raises when enforced + empty workspace_id; passes through when not enforced) — closes the "flag exists but nothing tests it" gap

## Verification — DONE
- [x] Full suite: `215 passed, 2 skipped` (213 prior + 2 new), 0 failures

## Batch K — OpenSearch reconciliation job (closes "explicitly deferred" gap) — DONE
- [x] `app/opensearch/reconcile.py` (new) — `reconcile_workspace()` / `reconcile_all_workspaces()`. Scans Postgres `document_chunk` for each workspace's *active* `embedding_version` (via `get_index_state`), `mget`s the deterministic OpenSearch `_id`s, and re-drives only chunks OpenSearch is missing via the existing `bulk_upsert()`. Deliberately one-directional — never deletes (no tombstone concept in Postgres, `delete_by_document()` is untested dead code, see below)
- [x] `app/core/observability.py` — added `RECONCILE_RUNS` / `RECONCILE_CHUNKS_REPAIRED` Prometheus counters, same pattern as `INGEST_JOBS`
- [x] `scripts/reconcile_opensearch.py` (new) — CLI wrapper, `--workspace` for a single tenant or all workspaces by default
- [x] `k8s/cronjob-opensearch-reconcile.yaml` (new) — runs every 15 min, follows the existing `cronjob-drift.yaml` template and `worker-deployment.yaml`'s secret wiring
- [x] `tests/test_opensearch_reconcile.py` (new, 7 tests) — skip branches (dual-write disabled / OS unavailable), repairs only the missing chunk, no-op when nothing missing, scopes strictly to active embedding_version (not target/stale versions), repair failure recorded not raised, and a structural assertion that the module never imports `delete_by_document`
- [x] `docs/opensearch_design.md`, `README.md`, `docs/demo-script.md` — updated to describe the reconciliation job instead of "explicitly deferred", refreshed 213 → 222 test count

### Explicitly still out of scope (documented in the module docstring, not silently dropped)
- Pruning OpenSearch-side orphans (docs with no matching Postgres row) — requires a real, tested document-delete feature first; `delete_by_document()` has zero callers/tests today and reconciliation must not be its first caller
- Content-drift detection (Postgres `chunk_hash` changed but OpenSearch copy is stale) — would need `chunk_hash` added to the OpenSearch `_source` schema; flagged as a follow-up, not silently absorbed into this job's scope

## Verification — DONE
- [x] Full suite: `222 passed, 2 skipped` (215 prior + 7 new), 0 failures
