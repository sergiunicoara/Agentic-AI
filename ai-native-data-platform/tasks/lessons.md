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

## Environment

- **PowerShell is not bash.** `curl -X` hits the `Invoke-WebRequest` alias,
  `for i in {1..5}` is a parser error, `docker compose exec` needs `-T` when
  stdin is redirected. Give the user PowerShell-native commands.
