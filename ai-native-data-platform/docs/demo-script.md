# AI-Native Data Platform — Demo Script

**Runtime:** ~4 min | **Stack:** FastAPI · pgvector · OpenSearch · Grafana · DSPy | **Tests:** 213 passing

> **Terminal note:** Two syntaxes below — pick the one matching your shell.
> - **PowerShell 5.1:** commands use `curl.exe --%` (stop-parsing token prevents PS from mangling args)
> - **cmd.exe / Git Bash / any other shell:** use the `curl` commands in the *"cmd / bash"* blocks — no `--%`, same `\"` escaping, works natively

---

## S01 — INT. TERMINAL — COLD OPEN `0:00 – 0:15`

Screen dark. Cursor blinks. No title card. One command.

```
docker compose up -d
```

```
[+] Running 8/8
 ✔ Container ai-native-data-platform-db-1                    Started
 ✔ Container ai-native-data-platform-redis-1                 Started
 ✔ Container ai-native-data-platform-opensearch-1            Healthy
 ✔ Container ai-native-data-platform-api-1                   Started
 ✔ Container ai-native-data-platform-worker-1                Started
 ✔ Container ai-native-data-platform-prometheus-1            Started
 ✔ Container ai-native-data-platform-grafana-1               Started
 ✔ Container ai-native-data-platform-alertmanager-1          Started
```

**V.O.:** *"A production-grade RAG platform. Eight services. One command. Let's see what it does."*

> ↳ Init schema (first run only):
> ```
> Get-Content scripts/init_db.sql | docker exec -i ai-native-data-platform-db-1 psql -U app -d app
> ```

---

## S02 — INT. TERMINAL — INGESTION PIPELINE `0:15 – 0:55`

Split screen: curl request left pane, API logs right pane.

> Note: ingestion is written to a durable Postgres job queue. Logs and retry
> attempts appear in the worker container, and jobs survive an API restart.

**PowerShell:**
```
curl.exe --% -s -X POST http://localhost:8000/ingest/transcript -H "Content-Type: application/json" -H "X-Workspace-Id: demo" -H "X-API-Key: demo" -d "{\"workspace_id\":\"demo\",\"title\":\"Refund Policy\",\"text\":\"Customers may request a full refund within 30 days of purchase.\"}"
```
**cmd / bash:**
```
curl -s -X POST http://localhost:8000/ingest/transcript -H "Content-Type: application/json" -H "X-Workspace-Id: demo" -H "X-API-Key: demo" -d "{\"workspace_id\":\"demo\",\"title\":\"Refund Policy\",\"text\":\"Customers may request a full refund within 30 days of purchase.\"}"
```

```json
{
  "status": "queued",
  "document_id": "3f8a2c91-..."
}
```

```
docker logs ai-native-data-platform-api-1 --follow
```

```
{"name":"ingest_enqueued",        "document_id":"3f8a2c91-...", "workspace_id":"demo"}
{"name":"opensearch_connected",   "version":"2.12.0",           "cluster":"docker-cluster"}
{"name":"opensearch_bulk_upsert", "indexed":1, "errors":0,      "latency_ms":94}
```

**V.O.:** *"Chunked, embedded, written to pgvector — then dual-synced to OpenSearch in a single bulk call, after the Postgres transaction commits. Re-ingest the same document and you get one row, one OpenSearch doc. The dedup key is deterministic: `document_id:chunk_index:embedding_version`. No duplicates, ever."*

> **Graph path:** `ingest_transcript()` → `process_document()` → `write_session_scope()` + `_opensearch_dual_write_batch()` → `bulk_upsert()`. Dual-write sits outside the `with` block — never holds a DB connection open.

---

## S03 — INT. TERMINAL — RAG: ASK A QUESTION `0:55 – 1:35`

Fresh terminal. Ask the platform about the just-ingested document.

**PowerShell:**
```
curl.exe --% -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -H "X-Workspace-Id: demo" -H "X-API-Key: demo" -d "{\"workspace_id\":\"demo\",\"query\":\"How many days do customers have to request a refund?\"}"
```
**cmd / bash:**
```
curl -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -H "X-Workspace-Id: demo" -H "X-API-Key: demo" -d "{\"workspace_id\":\"demo\",\"query\":\"How many days do customers have to request a refund?\"}"
```

```json
{
  "answer": "Customers have 30 days to request a refund.",
  "citations": [{ "chunk_id": "aeb53653-...", "snippet": "Customers may request a full refund within 30 days of purchase." }],
  "unknown": false
}
```

**PAUSE ON** `"unknown": false` — the anti-hallucination contract. Hold 2s.

**V.O.:** *"Query embeds. Redis cache miss. OpenSearch BM25 retrieves. LLM generates. The citation verifier confirms the snippet exists in the retrieved chunk, word-for-word. Groundedness passes. If it doesn't — `unknown: true`. The platform degrades safely. It never hallucinates."*

---

## S04 — INT. TERMINAL — SWITCH RETRIEVAL BACKEND LIVE `1:35 – 1:55`

Same request body. One extra header. Different engine. Result is identical.

**PowerShell:**
```
curl.exe --% -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -H "X-Workspace-Id: demo" -H "X-API-Key: demo" -H "X-Experiment: opensearch_hybrid" -d "{\"workspace_id\":\"demo\",\"query\":\"How many days do customers have to request a refund?\"}"
```
**cmd / bash:**
```
curl -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" -H "X-Workspace-Id: demo" -H "X-API-Key: demo" -H "X-Experiment: opensearch_hybrid" -d "{\"workspace_id\":\"demo\",\"query\":\"How many days do customers have to request a refund?\"}"
```

```json
{
  "answer": "Customers may request a full refund within 30 days of purchase.",
  "citations": [...],
  "unknown": false
}
```

**V.O.:** *"One header. Eight retrieval modes — pgvector dense, lexical, hybrid, multimodal; or OpenSearch BM25, vector, or hybrid with RRF in Python. No code change. Same API contract."*

---

## S05 — INT. TERMINAL — DSPy NL→SQL `1:55 – 2:25`

Plain English → workspace-scoped parameterized SQL.

**PowerShell:**
```
curl.exe --% -s -X POST http://localhost:8000/query/natural-language -H "Content-Type: application/json" -H "X-Workspace-Id: demo" -H "X-API-Key: demo" -d "{\"workspace_id\":\"demo\",\"query\":\"Show the 5 slowest traces\"}"
```
**cmd / bash:**
```
curl -s -X POST http://localhost:8000/query/natural-language -H "Content-Type: application/json" -H "X-Workspace-Id: demo" -H "X-API-Key: demo" -d "{\"workspace_id\":\"demo\",\"query\":\"Show the 5 slowest traces\"}"
```

```json
{
  "sql": "SELECT id, trace_type, workspace_id, latency_ms, created_at FROM trace_log WHERE workspace_id = :_workspace_id ORDER BY latency_ms DESC LIMIT 5",
  "results": [],
  "row_count": 0
}
```

**V.O.:** *"DSPy ChainOfThought extracts a structured QueryIntent. A normalization layer handles LLM output quirks — table aliases, column hallucinations, COUNT(*) normalization. Parameterized SQL, workspace-scoped, 5-second statement timeout, every query audit-logged. Optimized against a 20-example golden dataset with BootstrapFewShot — no hand-written prompts."*

> **God node:** `QueryIntent` — 51 edges connecting `NLToIntent`, `_normalize_data()`, `build_sql()`, `validate_intent()`, `execute_query()`, `write_audit_log()`, and the full test suite.

---

## S06 — INT. BROWSER — GRAFANA OBSERVABILITY `2:25 – 2:55`

Browser → **http://localhost:3000** (admin / admin) → Dashboards → Platform Overview. Navigate slowly.

- **Panel 1:** RPS counter + p50/p95/p99 latency histogram. Hover a bar.
- **Panel 2:** Rolling SLO window — error rate, unknown rate, p95 with threshold markers.
- **Panel 3:** EWMA anomaly scores — latency z-score and error z-score. Point at the 6.0 threshold line.
- **Panel 4:** Ingestion job counts by status + OpenSearch latency histograms.

```
curl.exe -s http://localhost:8000/metrics | Select-String "slo_rolling|anomaly_score"
```

```
slo_rolling_p95_latency_ms 312.0
slo_rolling_error_rate 0.0
slo_rolling_unknown_rate 0.0
platform_anomaly_score{signal="p95_latency_ms"} 0.82
platform_anomaly_score{signal="error_rate"} 0.14
```

**V.O.:** *"Prometheus scrapes every 10 seconds. Rolling SLO window holds the last 2,000 requests — p95, error rate, unknown rate on every observation. EWMA detectors surface anomalies before they trip a threshold. When a z-score exceeds 6.0, an event fires. If it sustains — the remediation controller activates."*

---

## S07 — INT. EDITOR — AUTO-REMEDIATION CONTROLLER `2:55 – 3:25`

Open **`app/core/reliability/remediation_controller.py`**. Walk lines 51–86.

- **L54:** `try_acquire(lock)` — Postgres advisory lock; only the leader runs remediation
- **L73:** `snap.get("samples", 0) < min_samples` — waits for 200 observations before activating
- **L83:** `violated = violated + 1 if bad else max(0, violated - 1)` — hysteresis, not a toggle
- **L85:** `if violated >= 3: _write_override(force_experiment)` — forces all traffic to control

> Note: the override file only exists after 3 consecutive SLO violations. In a healthy system it's absent — simulate it manually for the demo.

**PowerShell:**
```
docker compose exec db psql -U app -d app -c "INSERT INTO runtime_experiment_override (scope, experiment) VALUES ('global', 'control') ON CONFLICT (scope) DO UPDATE SET experiment = EXCLUDED.experiment, updated_at = now();"
docker compose exec db psql -U app -d app -c "SELECT scope, experiment, updated_at FROM runtime_experiment_override;"
```
**cmd (via inline PowerShell):**
```
powershell -Command "New-Item -ItemType Directory -Force .runtime | Out-Null; '{ \"force_all\": \"control\", \"ts\": 1720600000.0 }' | Set-Content .runtime\ab_override.json; Get-Content .runtime\ab_override.json"
```

```json
{ "force_all": "control", "ts": 1720600000.0 }
```

**PowerShell:**
```
docker compose exec db psql -U app -d app -c "DELETE FROM runtime_experiment_override WHERE scope = 'global';"
```
**cmd:**
```
docker compose exec db psql -U app -d app -c "DELETE FROM runtime_experiment_override WHERE scope = 'global';"
```

**V.O.:** *"Leader-elected via Postgres advisory lock — in a multi-replica deployment, only one instance runs remediation. Three consecutive SLO violations write a JSON override, forcing all workspace traffic to the safe control experiment. Reversible: delete the file. Closed-loop ops in 100 lines of Python."*

---

## S08 — INT. TERMINAL — TEST SUITE `3:25 – 3:45`

```
pytest tests/ -q
```

```
................................ [ 14%]
................................ [ 29%]
................................ [ 44%]
................................ [ 59%]
................................ [ 74%]
................................ [ 89%]
.....................ss          [100%]

213 passed, 2 skipped in 8.75s
```

**PAUSE ON** "213 passed" — hold 2 seconds before cutting.

**V.O.:** *"213 tests. No live database or OpenSearch required — mocks injected at import time. Coverage: OpenSearch idempotency, prompt injection in five taxonomies, PII redaction, DSPy normalization edge cases, SQL builder for every filter operator, reliability contracts, rolling SLO, token bucket, chaos degradation when providers fail, remediation hysteresis, and the retrieval cache's index-epoch invalidation."*

---

## S09 — INT. BROWSER — KNOWLEDGE GRAPH `3:45 – 4:00`

Open **`graphify-out/graph.html`** in a browser. Zoom out to show the full graph, then hover god nodes.

- **HOVER** RetrievedChunk (61 edges) — schema type every retrieval path returns
- **HOVER** QueryIntent (51 edges) — NL→SQL central abstraction
- **HOVER** emit_event() (31 edges) — observability wired through every subsystem

**V.O.:** *"895 nodes. 1929 edges. 80 communities. Production patterns, not portfolio scaffolding."*

---

## FADE OUT

| Services | Retrieval Modes | Tests | Graph Nodes | Hallucinations |
|---|---|---|---|---|
| 8 | 8 | 213 | 895 | 0 |
