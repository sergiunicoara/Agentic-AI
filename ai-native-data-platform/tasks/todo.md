# Fix plan — 2026-09-25

Source: follow-up audit (see conversation). Scope: Critical + High findings only
(Medium/Low items deliberately deferred per user's "fix them" following that
scoping question). Verified against a real Postgres 16 + pgvector instance,
not the mocked test suite.

## Critical

- [x] C1 — `:b::jsonb` / `:params::jsonb` aren't valid SQLAlchemy bind syntax;
      Postgres raises a syntax error and it's swallowed by a bare `except`.
      `trace_log` and `nl_query_audit_log` never actually get written.
      Fix: `CAST(:b AS jsonb)` in `observability.py` and `nl_query/audit.py`.
- [x] C2 — `docker-compose.yml` makes `POSTGRES_USER=app` the bootstrap
      superuser; RLS is bypassed for superusers/owners, so tenant isolation
      is enforced only by the `WHERE workspace_id` predicates, not by RLS at
      all. Fix: bootstrap as `postgres`, create a non-superuser `app` login
      role with explicit grants (not ownership) on the tables, keep RLS.
- [x] C3 — `enforce_latency(latency_ms, contract)` at the end of `/ask`
      applies the 800ms ceiling to the *whole* request including the LLM
      call, so with a real LLM every answer with a real (non-mock) call over
      the ceiling silently degrades to "unknown". Split online contract into
      a retrieval budget and a full-request ceiling that's realistic for a
      real LLM roundtrip.
- [x] C4 — CI workflows live at `ai-native-data-platform/.github/workflows`;
      GitHub only discovers workflows at the repo root. Move them so they
      actually run, and fix `eval-gates.yml` to seed a document before
      running the eval harness (currently seeds only the empty demo
      workspace, so pgvector eval has zero retrievable chunks).
- [x] C5 — `id = ANY(:ids)` compares `uuid = text` and Postgres rejects it
      (`app/indexing/pipeline.py`). Bulk reindex/backfill always fails.
      Fix: `CAST(:ids AS uuid[])`.
- [x] C6 — `NLToIntent`'s "docstring" is an f-string, so Python does not
      treat it as `__doc__`; DSPy falls back to a generic instruction and
      never sees the schema. Fix: use a real (still-interpolated) docstring
      DSPy can read via `dspy.Signature.__doc__`.

## High

- [x] H1 — Bulk indexing path (`app/indexing/pipeline.py::run_manifest`)
      writes a freshly generated `chunk_id` to OpenSearch even when the
      Postgres insert hit `ON CONFLICT DO NOTHING` (row already existed) —
      the two stores then reference different ids for the same chunk.
      Fix: switch the flush to per-row insert with `RETURNING`, mirroring
      the online ingestion path, and only dual-write inserted rows.
- [x] H2 — Online ingestion (`ingestion/pipeline.py`, `ingestion/multimodal.py`)
      tags new chunks with `settings.embedding_version` (a process-level env
      default) instead of the workspace's actual active embedding version,
      so newly ingested documents can silently become invisible to
      retrieval after a reindex cutover. Fix: read
      `get_index_state(workspace_id).active_embedding_version`.
- [x] H3 — `/ingest/image` PDF handling has no page cap, runs the blocking
      pdf2image conversion inline on the event loop, and the Dockerfile
      never installs poppler (pdf2image's hard system dependency) — PDF
      ingestion is currently broken in the shipped container image on top
      of being a DoS vector. Fix: cap page count, offload to a thread, add
      poppler-utils to the Dockerfile.
- [x] H4 — Per-workspace rate limiting runs in middleware *before*
      authentication, keyed off the unauthenticated `X-Workspace-Id` header,
      so anyone can exhaust another workspace's quota with a bad API key.
      Fix: enforce the token bucket only after `require_workspace_key`
      succeeds.
- [x] H5 — `/ask` only catches `ReliabilityViolation` around
      `pipeline.run()`; a raw DB/OpenSearch exception (timeout, connection
      error) propagates as an HTTP 500 instead of degrading to the safe
      "unknown" fallback the rest of the endpoint is built around.
- [x] H6 — `k8s/networkpolicy.yaml`'s allow-internal policy selects
      `app: ai-platform`, but the deployments are labelled
      `ai-platform-api` / `ai-platform-worker`; only the default-deny
      policy actually matches those pods, so applying these manifests as
      written blocks the API/worker pods' egress (DNS, DB, Redis,
      OpenSearch, OpenAI) entirely.
- [x] H7 — `/ingest/transcript` inserts the `document` row and enqueues the
      `ingestion_job` row in two separate transactions; a failure between
      them leaves a document that's permanently stuck (never queued, and
      re-POSTing just returns `already_ingested`). Fix: enqueue the job in
      the same transaction as the document insert.

## Verification

- [x] Real Postgres 16 + pgvector instance (scratch, not part of the repo)
      used to reproduce each bug before the fix and confirm after.
- [x] Existing mocked unit suite (`pytest tests/`) still green.
- [x] New/extended tests added where the existing mock-everything
      `conftest.py` was the reason the bug shipped in the first place.

## Review

All 13 findings (C1-C6, H1-H7) fixed and verified. Final:
`pytest tests/` — 222 passed, 1 skipped (skip is "no live OPENSEARCH_URL",
unaffected by this pass).

Each fix's own commit message has the specific real-Postgres/real-app
verification steps; summary:

- **C1** (jsonb bind syntax) — `CAST(:x AS jsonb)` in both write paths;
  confirmed real inserts now succeed and failures are no longer silently
  swallowed.
- **C2** (RLS bypassed by superuser) — bootstrap as `postgres`, app runs as
  a real non-superuser role; confirmed cross-workspace reads return 0 rows
  and cross-workspace writes are rejected by the RLS policy itself.
- **C3** (retrieval-only ceiling applied to the whole request) — split into
  `max_request_latency_ms` (retrieval) and `max_end_to_end_latency_ms`
  (full request); remediation controller's threshold now derives from the
  latter to match what it actually observes.
- **C4** (CI never ran) — workflows moved to the repo root
  (`.github/workflows/`, this being a multi-project monorepo so scoped by
  `paths:`); `eval-gates.yml` now seeds real content and runs `pytest`;
  confirmed the eval harness exits 0 with `gates_ok=true` against a real
  Postgres instance end to end.
- **C5** (`uuid = text` in bulk reindex) — `CAST(:ids AS uuid[])`; confirmed
  against real Postgres.
- **C6** (DSPy instructions silently dropped) — f-string docstrings aren't
  captured by Python as `__doc__`; fixed by assigning it explicitly, and
  patched the already-compiled `compiled_intent.json` in place (keeping its
  4 bootstrapped demos) so it doesn't re-apply the same bug on load.
- **H1** (bulk path could dual-write a chunk id OpenSearch never actually
  got from Postgres) — switched the flush to a single multi-row INSERT
  with RETURNING (executemany doesn't support this reliably via psycopg2 —
  confirmed empirically); only genuinely-inserted rows are dual-written,
  using the id Postgres assigned.
- **H2** (new chunks tagged with the stale env embedding version instead of
  the workspace's active one) — read `get_index_state(workspace_id)` at
  ingestion time in both the text and multimodal paths.
- **H3** (PDF ingestion: no page cap, blocked the event loop, and poppler
  was missing from the image entirely) — added `max_pdf_pages` (pdfinfo
  checked before any rasterization), moved the conversion to a threadpool,
  added `poppler-utils` to the Dockerfile.
- **H4** (rate limiting ran before auth, keyed off the unauthenticated
  header) — moved into `require_workspace_key`, after the API key is
  validated; confirmed an unauthenticated attacker can no longer drain a
  real workspace's quota, and that real over-quota traffic is still
  rate-limited.
- **H5** (`/ask` 500'd on a raw infra failure instead of degrading) — added
  a broad `except Exception` alongside the existing `ReliabilityViolation`
  handling; confirmed with a real forced Postgres statement-timeout error.
- **H6** (NetworkPolicy selector didn't match either deployment's labels)
  — `matchExpressions` covering both real label values (a pod can't carry
  two values for the same `app` key, so a shared label wasn't an option
  without also touching each Deployment's own selector).
- **H7** (document insert + job enqueue were two separate transactions) —
  enqueue now shares the same session/transaction as the document insert;
  confirmed atomic (forcing the enqueue to fail rolls back the document
  insert too — no orphaned document row).

### Noted but deliberately not fixed in this pass (out of the agreed scope)

- `k8s/eval-job.yaml` and `k8s/cronjob-drift.yaml` carry no `app` label at
  all, so — separately from the H6 fix above — they're *also* not covered
  by the allow-internal NetworkPolicy and would have no DB/network access
  if the policies were applied as written. Not part of the original H6
  finding; flagging for a follow-up rather than expanding this pass's
  scope.
- Everything in the Medium/Low list from the audit this plan is based on
  (eval golden-dataset chunk ids being inherently non-deterministic given
  random chunk uuids, MMR/vector-search performance, OpenSearch TLS
  verification, NL→SQL error message leakage, etc.) — explicitly deferred
  per scope agreed before this pass started.
