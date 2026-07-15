# AI-Native Data Platform — Demo Script

**Runtime:** ~4 min | **Stack:** FastAPI · pgvector · OpenSearch · Grafana · DSPy | **Tests:** 190 passing

---

## S01 — INT. TERMINAL — COLD OPEN `0:00 – 0:15`

Screen dark. Cursor blinks. No title card. One command.

**SHOT:** Full-screen terminal. Compose output animates in line by line.

```bash
$ docker compose up -d

[+] Running 8/8
 ✔ Container db            Started
 ✔ Container redis          Started
 ✔ Container opensearch     Started
 ✔ Container api            Started
 ✔ Container worker         Started
 ✔ Container prometheus     Started
 ✔ Container grafana        Started
 ✔ Container alertmanager   Started
```

**V.O.:** *"A production-grade RAG platform. Eight services. One command. Let's see what it does."*

> ↳ Init schema: `docker compose exec -T db psql -U app -d app < scripts/init_db.sql`

---

## S02 — INT. TERMINAL — INGESTION PIPELINE `0:15 – 0:55`

Split screen: curl request left pane, worker logs right pane. Watch the chain fire.

```bash
# LEFT PANE
$ curl -s -X POST http://localhost:8000/ingest/transcript \
  -H "Content-Type: application/json" \
  -H "X-Workspace-Id: demo" \
  -H "X-API-Key: demo" \
  -d '{
    "workspace_id": "demo",
    "title": "Refund Policy",
    "text": "Customers may request a full refund within 30 days of purchase."
  }' | jq

{
  "status": "queued",
  "document_id": "3f8a2c91-..."
}
```

```
# RIGHT PANE — worker logs
worker  | event=ingestion_started      doc=3f8a2c91 chunks=1
worker  | event=chunk_embedded         idx=0 version=v1 ms=41
worker  | event=chunk_inserted         rows=1 conflict=0
worker  | event=opensearch_dual_write  indexed=1 errors=0
worker  | event=ingestion_complete     latency_ms=94
```

**V.O.:** *"Chunked, embedded, written to pgvector — then dual-synced to OpenSearch in a single bulk call, after the Postgres transaction commits. Re-ingest the same document and you get one row, one OpenSearch doc. The dedup key is deterministic: `document_id:chunk_index:embedding_version`. No duplicates, ever."*

> **Graph path:** `ingest_transcript()` → `process_document()` → `write_session_scope()` + `_opensearch_dual_write_batch()` → `bulk_upsert()`. Dual-write sits outside the `with` block — never holds a DB connection open.

---

## S03 — INT. TERMINAL — RAG: ASK A QUESTION `0:55 – 1:35`

Fresh terminal. Ask the platform about the just-ingested document.

```bash
$ curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -H "X-Workspace-Id: demo" \
  -H "X-API-Key: demo" \
  -d '{"workspace_id":"demo","query":"How long to get a refund?"}' | jq

{
  "answer":    "You have 30 days from the date of purchase to request a full refund.",
  "citations": [{ "chunk_id": "3f8a2c91:0:v1", "snippet": "full refund within 30 days" }],
  "unknown":   false,
  "latency_ms": 312
}
```

**PAUSE ON** `"unknown": false` — the anti-hallucination contract. Hold 2s.

**V.O.:** *"Query embeds. Redis cache miss. pgvector ANN + BM25 lexical fire in parallel, fused via RRF, reranked with MMR. LLM generates. The citation verifier confirms the snippet exists in the retrieved chunk, word-for-word. Groundedness passes 0.70. If it doesn't — `unknown: true`. The platform degrades safely. It never hallucinates."*

---

## S04 — INT. TERMINAL — SWITCH RETRIEVAL BACKEND LIVE `1:35 – 1:55`

Same request body. One env var. Different engine. Result is identical.

```bash
# Same request — now routed to OpenSearch BM25 + kNN + RRF
$ RETRIEVAL_MODE=opensearch_hybrid \
  curl -s -X POST http://localhost:8000/ask \
  -H "X-Workspace-Id: demo" -H "X-API-Key: demo" \
  -d '{"workspace_id":"demo","query":"How long to get a refund?"}' \
  | jq '.answer,.unknown,.latency_ms'

"You have 30 days from the date of purchase to request a full refund."
false
298
```

**V.O.:** *"One env var. Eight retrieval modes — pgvector dense, lexical, hybrid, multimodal; or OpenSearch BM25, vector, or hybrid with RRF in Python. No code change. Same API contract."*

---

## S05 — INT. TERMINAL — DSPy NL→SQL `1:55 – 2:25`

Plain English → workspace-scoped parameterized SQL. Generated SQL visible in response.

```bash
$ curl -s -X POST http://localhost:8000/query/natural-language \
  -H "X-Workspace-Id: demo" -H "X-API-Key: demo" \
  -d '{"workspace_id":"demo","query":"Show the 5 slowest traces"}' | jq

{
  "sql": "SELECT id, trace_type, workspace_id, latency_ms, created_at
          FROM trace_log
          WHERE workspace_id = :_workspace_id
          ORDER BY latency_ms DESC LIMIT 5",
  "row_count": 5,
  "results": [...]
}
```

**V.O.:** *"DSPy ChainOfThought extracts a structured QueryIntent. A normalization layer handles LLM output quirks — table aliases, column hallucinations, COUNT(*) normalization. Parameterized SQL, workspace-scoped, 5-second statement timeout, every query audit-logged. Optimized against a 20-example golden dataset with BootstrapFewShot — no hand-written prompts."*

> **God node:** `QueryIntent` — 51 edges connecting `NLToIntent`, `_normalize_data()`, `build_sql()`, `validate_intent()`, `execute_query()`, `write_audit_log()`, and the full test suite.

---

## S06 — INT. BROWSER — GRAFANA OBSERVABILITY `2:25 – 2:55`

Browser → **http://localhost:3000** → Dashboards → Platform Overview. Navigate slowly.

- **Panel 1:** RPS counter + p50/p95/p99 latency histogram. Hover a bar.
- **Panel 2:** Rolling SLO window — error rate, unknown rate, p95 with threshold markers (800 ms / 25% / 35%).
- **Panel 3:** EWMA anomaly scores — latency z-score and error z-score. Point at the 6.0 threshold line.
- **Panel 4:** Ingestion job counts by status + OpenSearch latency histograms (BM25 / vector / hybrid separate).

```bash
# Check metrics directly
$ curl -s http://localhost:8000/metrics | grep "anomaly_score\|slo_rolling"

anomaly_score{detector="latency"}    0.82
anomaly_score{detector="error_rate"} 0.14
slo_rolling_p95_latency_ms           312.0
slo_rolling_error_rate               0.0
```

**V.O.:** *"Prometheus scrapes every 10 seconds. Fifteen panels. Rolling SLO window holds the last 2,000 requests — p95, error rate, unknown rate on every observation. EWMA detectors surface anomalies before they trip a threshold. When a z-score exceeds 6.0, an event fires. If it sustains — the remediation controller activates."*

---

## S07 — INT. EDITOR — AUTO-REMEDIATION CONTROLLER `2:55 – 3:25`

Open **`app/core/reliability/remediation_controller.py`**. Walk lines 51–86.

- **L54:** `try_acquire(lock)` — Postgres advisory lock; only the leader runs remediation
- **L73:** `snap.get("samples", 0) < min_samples` — waits for 200 observations before activating
- **L83:** `violated = violated + 1 if bad else max(0, violated - 1)` — hysteresis, not a toggle
- **L85:** `if violated >= 3: _write_override(force_experiment)` — forces all traffic to control

```bash
# After 3 consecutive SLO violations:
$ cat .runtime/ab_override.json
{
  "force_all": "control",
  "ts": 1720600000.0
}

# Restore normal routing — no deployment needed:
$ rm .runtime/ab_override.json
```

**V.O.:** *"Leader-elected via Postgres advisory lock — in a multi-replica deployment, only one instance runs remediation. Three consecutive SLO violations write a JSON override, forcing all workspace traffic to the safe control experiment. Reversible: delete the file. Audited: every activation emits an event. Closed-loop ops in 100 lines of Python."*

---

## S08 — INT. TERMINAL — TEST SUITE `3:25 – 3:45`

New terminal. Run the full suite. No commentary until the summary line.

```bash
$ pytest tests/ -q

................................ [ 16%]
................................ [ 33%]
................................ [ 50%]
................................ [ 66%]
................................ [ 83%]
.......................ss        [ 99%]
.                               [100%]

190 passed, 2 skipped in 4.3s
```

**PAUSE ON** "190 passed" — hold 2 seconds before cutting.

**V.O.:** *"190 tests. No live database or OpenSearch required — mocks injected at import time. Coverage: OpenSearch idempotency and availability re-probe, prompt injection in five taxonomies, PII redaction, DSPy normalization edge cases, SQL builder for every filter operator, reliability contracts, rolling SLO, token bucket, and chaos degradation when providers fail."*

---

## S09 — INT. BROWSER — KNOWLEDGE GRAPH `3:45 – 4:00`

Open **`graphify-out/graph.html`**. Zoom out to show the full graph, then hover god nodes.

- **HOVER** RetrievedChunk (61 edges) — schema type every retrieval path returns
- **HOVER** QueryIntent (51 edges) — NL→SQL central abstraction
- **HOVER** emit_event() (31 edges) — observability wired through every subsystem

**V.O.:** *"891 nodes. 1924 edges. 78 communities. Production patterns, not portfolio scaffolding."*

---

## FADE OUT

| Services | Retrieval Modes | Tests | Graph Nodes | Hallucinations |
|---|---|---|---|---|
| 8 | 8 | 190 | 891 | 0 |
