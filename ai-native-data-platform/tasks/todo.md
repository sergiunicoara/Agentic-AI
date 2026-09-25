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

- [ ] H1 — Bulk indexing path (`app/indexing/pipeline.py::run_manifest`)
      writes a freshly generated `chunk_id` to OpenSearch even when the
      Postgres insert hit `ON CONFLICT DO NOTHING` (row already existed) —
      the two stores then reference different ids for the same chunk.
      Fix: switch the flush to per-row insert with `RETURNING`, mirroring
      the online ingestion path, and only dual-write inserted rows.
- [ ] H2 — Online ingestion (`ingestion/pipeline.py`, `ingestion/multimodal.py`)
      tags new chunks with `settings.embedding_version` (a process-level env
      default) instead of the workspace's actual active embedding version,
      so newly ingested documents can silently become invisible to
      retrieval after a reindex cutover. Fix: read
      `get_index_state(workspace_id).active_embedding_version`.
- [ ] H3 — `/ingest/image` PDF handling has no page cap, runs the blocking
      pdf2image conversion inline on the event loop, and the Dockerfile
      never installs poppler (pdf2image's hard system dependency) — PDF
      ingestion is currently broken in the shipped container image on top
      of being a DoS vector. Fix: cap page count, offload to a thread, add
      poppler-utils to the Dockerfile.
- [ ] H4 — Per-workspace rate limiting runs in middleware *before*
      authentication, keyed off the unauthenticated `X-Workspace-Id` header,
      so anyone can exhaust another workspace's quota with a bad API key.
      Fix: enforce the token bucket only after `require_workspace_key`
      succeeds.
- [ ] H5 — `/ask` only catches `ReliabilityViolation` around
      `pipeline.run()`; a raw DB/OpenSearch exception (timeout, connection
      error) propagates as an HTTP 500 instead of degrading to the safe
      "unknown" fallback the rest of the endpoint is built around.
- [ ] H6 — `k8s/networkpolicy.yaml`'s allow-internal policy selects
      `app: ai-platform`, but the deployments are labelled
      `ai-platform-api` / `ai-platform-worker`; only the default-deny
      policy actually matches those pods, so applying these manifests as
      written blocks the API/worker pods' egress (DNS, DB, Redis,
      OpenSearch, OpenAI) entirely.
- [ ] H7 — `/ingest/transcript` inserts the `document` row and enqueues the
      `ingestion_job` row in two separate transactions; a failure between
      them leaves a document that's permanently stuck (never queued, and
      re-POSTing just returns `already_ingested`). Fix: enqueue the job in
      the same transaction as the document insert.

## Verification

- [ ] Real Postgres 16 + pgvector instance (scratch, not part of the repo)
      used to reproduce each bug before the fix and confirm after.
- [ ] Existing mocked unit suite (`pytest tests/`) still green.
- [ ] New/extended tests added where the existing mock-everything
      `conftest.py` was the reason the bug shipped in the first place.
