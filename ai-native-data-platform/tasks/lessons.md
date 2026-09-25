# Lessons

Patterns captured from real bugs and audit findings in this repo. Review at session start.

## Dual-store consistency (OpenSearch audit, 2026-04)

- **Two stores must share one conflict key.** Postgres deduped on
  `(document_id, chunk_index, embedding_version)` while OpenSearch used a fresh
  `uuid4()` as `_id` — every re-ingest duplicated chunks in OpenSearch only.
  Rule: when mirroring writes, derive the mirror's `_id` deterministically from
  the same columns as the primary's conflict key, and gate the mirror write on
  whether the primary actually inserted (`ON CONFLICT ... RETURNING id`).
- **"After commit" must mean after commit.** The dual-write comment claimed
  post-commit/fire-and-forget but the call sat inside `with write_session_scope()`,
  holding a pooled connection through tenacity retries and mirroring rows from
  transactions that could roll back. Rule: collect payloads inside the
  transaction, flush them in one bulk call after the `with` block exits.
- **Availability flags need a re-probe path.** The client cached `_available=False`
  permanently if OpenSearch was down at first touch (API boots faster than the
  JVM). Rule: any "is the dependency up?" singleton needs a cooldown re-probe so
  startup-order outages self-heal without a process restart.

## Reliability / SLO (2026-06)

- **A consumer reading a key the producer never sets is silent dead code.**
  `remediation_controller.py` gated on `snap.get("samples", 0) < min_samples`,
  but `RollingWindowSLO.snapshot()` never returned a `"samples"` key — so the
  gate was always `0 < 200` → always `True` → the remediation logic after it
  never ran, with no error anywhere. Rule: when a `.get(key, default)` exists,
  grep for where that dict is *built*, not just where it's read, and confirm
  the key is actually populated.

## Testing

- **Patch the usage site, not the definition site.** `from X import generate`
  creates a local binding; `monkeypatch.setattr("X.generate", ...)` doesn't reach
  it. Patch `"consumer_module.generate"` instead. (Bit us in chaos tests.)
- **Never neuter a failing test to make it pass.** A bulk-ingest test was rewritten
  into `assert {literal} == {literal}` — passed by construction, tested nothing.
  Fix the root cause (the empty-list guard sat *after* the library import) and
  keep the test calling the real function.
- **Unit-test SQL is not enough when SQL changed.** `RETURNING` with
  `ON CONFLICT DO NOTHING`, vector casts, and uuid/text comparisons only fail
  against real Postgres — smoke-test ingestion in Docker after touching ingestion SQL.

## SQLAlchemy + psycopg2

- **`:param::vector` breaks the named-parameter parser.** psycopg2 reads
  `:embedding::vector` as a bind named `embedding:` → syntax error at runtime.
  Use `CAST(:param AS vector)`.
- **`uuid = ANY(:text_list)` fails with "operator does not exist: uuid = text".**
  Cast the column: `id::text = ANY(:ids)`.

## OpenSearch

- **Verify settings apply to the chosen engine.** `knn.algo_param.ef_search` is
  nmslib-only; with the lucene engine it's inert config that documents a
  trade-off the cluster never makes. Same class of bug: defining an analyzer
  (`english_custom`) the mapping never references.
- **RRF in Python beats ML Commons pipelines for portability** — rank-based
  fusion doesn't care that BM25 and kNN scores aren't comparable, and it's
  testable without a cluster.

## DSPy (NL→SQL optimization, 2026-04)

- **Set `cache=False` on `dspy.LM` during optimization** — otherwise failed runs
  replay stale cached outputs (symptom: 0% accuracy at impossible it/s).
- **Normalize LLM output before Pydantic validation, not after.** Table/column/
  operator aliases, `SELECT *`, `COUNT(id)`, `limit: null` — one `_normalize_data`
  layer ahead of `model_validate` absorbs the whole taxonomy of hallucinations.
- **Ambiguous golden examples cap the optimizer.** Three "mismatches" were
  semantically valid alternative SQL; the fix was making the NL queries explicit
  ("…ordered by ingestion date"), not tweaking the prompt.

## Follow-up audit (2026-09-25)

- **The mocked test suite is blind to a whole class of bugs by design.**
  `tests/conftest.py` stubs `app.data.db` before any import, so
  `pytest tests/` (222 passed) never actually sends a query to Postgres.
  Three of this pass's Critical findings — `:x::jsonb` bind syntax,
  `uuid = ANY(:list)` type mismatch, and `INSERT ... RETURNING` silently
  returning nothing under executemany — were all real SQL bugs the mocked
  suite could not have caught even in principle, because a `MagicMock()`
  session accepts and "executes" any SQL string without ever parsing it.
  Rule: any PR that changes a raw SQL string needs a real-Postgres smoke
  test before merge, not just a green mocked suite — see "Unit-test SQL is
  not enough" above, which this pass re-confirmed the hard way.
- **`uuid = ANY(:list)` needs a cast on *some* side, not just when compared
  to a single value.** The existing lesson above (`id::text = ANY(:ids)`)
  covers casting the column; `app/indexing/pipeline.py`'s bulk-reindex doc
  fetch instead needed `id = ANY(CAST(:ids AS uuid[]))` (casting the bound
  array). Same root cause, opposite side — check both when reviewing a new
  `ANY(:...)` clause.
- **`INSERT ... RETURNING` against a list-of-dicts `text()` executemany
  does not reliably return rows via psycopg2** — confirmed empirically
  (`sqlalchemy.exc.ResourceClosedError: This result object does not return
  rows`). A single statement with an explicit multi-row `VALUES (...), (...)`
  and a flat params dict does. If you need per-row RETURNING from a batch
  insert with raw SQL, build the multi-row VALUES clause yourself; don't
  assume executemany-with-RETURNING works the way it does with a plain
  ORM/Core bulk insert.
- **A class-body f-string is not a docstring.** Python only captures a
  class body's first statement as `__doc__` when it's a literal string
  constant (`ast.Constant`); an f-string compiles to `ast.JoinedStr` and is
  silently dropped as a bare expression statement. `NLToIntent`'s DSPy
  signature had exactly this bug — the "docstring" never became
  `cls.__doc__`, and DSPy fell back to its own generic instructions with
  no error. Rule: never write `f"""..."""` in class-docstring position;
  build the string separately and assign `Cls.__doc__ = text` after the
  class if it needs interpolation.
- **RLS is bypassed for superusers *and* table owners, silently.**
  `docker-compose.yml` had `POSTGRES_USER=app` — the app connected as the
  schema-owning bootstrap superuser, so every `FORCE ROW LEVEL SECURITY`
  policy in `init_db.sql` was dead code and isolation rested entirely on
  `WHERE workspace_id` predicates in application SQL. Postgres gives no
  warning when a superuser's query silently ignores RLS. Rule: the role an
  application connects as must never be the same role that owns its
  tables; verify RLS with a real non-superuser connection, not just by
  reading the `CREATE POLICY` statements.
- **Rate limiting (or any per-identity quota) must key off a validated
  identity, not a client-supplied header.** The per-workspace token bucket
  ran in middleware before `require_workspace_key`'s credential check —
  anyone could drain a real workspace's quota by sending its id with a
  bogus API key. Rule: any quota, cache key, or audit-log entry keyed by a
  "workspace/user/tenant id" header must be enforced *after* that id is
  authenticated, never before.

## Environment

- **PowerShell is not bash.** `curl -X` hits the `Invoke-WebRequest` alias,
  `for i in {1..5}` is a parser error, `docker compose exec` needs `-T` when
  stdin is redirected. Give the user PowerShell-native commands.
