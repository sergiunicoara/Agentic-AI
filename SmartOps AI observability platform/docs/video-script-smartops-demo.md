# Demo Script — SmartOps: AI-Assisted Incident Response

> SmartOps compresses the on-call investigation loop from 20 minutes to 30 seconds:
> detect anomaly → run RCA → create ticket — human approves every step.

---

## Quick Start — 3 commands

```bash
# 1. Start infrastructure (Kafka KRaft, VictoriaMetrics, Elasticsearch, PostgreSQL)
docker-compose up -d

# 2. Start API + metric simulator
npm run dev:api        # Fastify 4 on :3000
npm run dev:simulator  # publishes JSON events to Kafka every 5s

# 3. Start frontend
npm run dev:web        # Next.js 14 on :3001
```

**Then open:**
- `http://localhost:3001/dashboard` — SmartOps UI
- `http://localhost:3002` — Grafana (same VictoriaMetrics data source)

---

## Preparation before recording

### A. Environment variables (`.env`)

```env
VICTORIA_METRICS_URL=http://localhost:8428
ELASTICSEARCH_URL=http://localhost:9200
KAFKA_BROKERS=localhost:9092
POSTGRES_URL=postgresql://smartops:smartops@localhost:5432/smartops
ANTHROPIC_API_KEY=sk-ant-...
SERVICENOW_INSTANCE=https://your-instance.service-now.com
SERVICENOW_USER=...
SERVICENOW_PASSWORD=...
JWT_SECRET_RS256_PRIVATE=...
```

### B. Verify services are healthy

```bash
docker ps
# Expected: kafka, victoriametrics, elasticsearch, postgres all running

curl http://localhost:8428/health   # VictoriaMetrics → {"status":"ok"}
curl http://localhost:9200/_cat/health  # Elasticsearch → green
```

### C. Seed baseline data (if first run)

The simulator needs ~2 minutes of baseline data before z-score detection works.
Start the simulator and wait before recording:

```bash
npm run dev:simulator
# Watch for: [METRIC] Published: us-east-1 | cpu | 34.2%
# Wait until you see at least 24 events (2 min of 5s intervals)
```

### D. Tabs to have open before recording

| Tab | URL | Purpose |
|-----|-----|---------|
| 1 | `localhost:3001/dashboard` | SmartOps UI — main demo surface |
| 2 | `localhost:3002` | Grafana — Golden Signals dashboard |
| 3 | Terminal running simulator | Watch for `[ANOMALY]` log line |
| 4 | `localhost:3001/incidents` | Incident history after approval |

---

## DEMO SCRIPT — English

### COLD OPEN (20s)

*On screen: title slide or blank — voice only.*

> "On-call engineer gets paged. They open Grafana, Kibana, Jaeger, the runbook —
> and spend 20 minutes manually correlating what happened.
> SmartOps compresses that to 30 seconds: detect, investigate, create a ticket —
> with a human approving every step."

---

### SCENE 1 — LIVE DASHBOARD (45s)

*Switch to `localhost:3001/dashboard`. Click through all three region tabs:
`us-east-1`, `eu-west-1`, `ap-southeast-1`.*

> "Three regions, five golden signals each — CPU, Memory, P99 Latency, Error Rate,
> Requests per second.
>
> Data comes from VictoriaMetrics via a Kafka fan-out pipeline: one producer publishes
> JSON events every 5 seconds, two independent consumer groups read the same topic —
> one writes to VictoriaMetrics, one bulk-indexes to Elasticsearch.
> The browser receives updates over Server-Sent Events every 2 seconds."

---

### SCENE 2 — THE SPIKE (30s)

*Keep Terminal visible. Wait for the log line:*
```
[ANOMALY] Injecting CPU spike → us-east-1
```
*Then switch to Grafana (`localhost:3002`) — CPU panel spikes within 10 seconds.*

> "The simulator just injected a CPU anomaly. Watch Grafana — same VictoriaMetrics
> data source the AI queries.
>
> This is what a traditional on-call engineer sees: a spike. Now watch what
> SmartOps does with it."

---

### SCENE 3 — AI DETECTS IT (30s)

*Switch to `localhost:3001` → AI Insights → click **Run AI Scan**.*

> "Six detection queries run in parallel — three regions, two metrics each.
> For each series it computes a z-score against the last 10 minutes of baseline.
>
> CPU at 92%, baseline mean 35%, z-score 3.8 — anomaly confirmed.
> Under a second, no model involved, purely deterministic math."

*On screen: red anomaly card — region, metric, current value vs baseline, z-score.*

*Click **Trigger RCA**.*

> "Now the LLM enters. A Mastra workflow kicks off — it queries VictoriaMetrics
> for correlated metrics, Elasticsearch for error logs, and a trace store for slow
> spans, all in parallel. Then Claude synthesizes the evidence into a root-cause
> hypothesis."

---

### SCENE 4 — THE DECISION (45s)

*On screen: approval modal — RCA summary, confidence score, correlated evidence,
remediation actions.*

> "The workflow suspended. It literally paused mid-execution, persisted state to
> PostgreSQL, and is waiting for a human. This isn't a UI convention — Mastra's
> suspend-resume is the execution model.
>
> The confidence score is 0.40 base, plus error logs times 0.02, plus trace spans
> times 0.03 — an honest signal about how much evidence the agent actually found."

*Read one line from the RCA summary on screen.*

> "Specific remediation actions — not 'check your infrastructure.'
> Let's approve it."

*Click **Approve**.*

> "Workflow resumes, step four fires — the ServiceNow agent creates a ticket.
> Incident row in PostgreSQL updates to 'ticketed' with the ticket ID.
>
> The AI touched nothing in production. It read, reasoned, and waited.
> A human with operator role made the call."

*On screen: incident history row — status = ticketed, INC number visible.*

---

### SCENE 5 — GRAFANA EVIDENCE (20s)

*Switch to `localhost:3002` → Golden Signals dashboard.*

> "Here's the same spike from the infrastructure side — the peak that triggered
> everything. In a traditional setup this is where the investigation starts.
> SmartOps already closed it."

---

### WRAP (30s)

> "Stack: Fastify 4 API, Next.js 14, VictoriaMetrics, Elasticsearch, Kafka KRaft,
> PostgreSQL, Mastra AI workflows with Claude. Auth is JWT RS256, RBAC enforced
> at the route level — viewers can't trigger workflows or approve tickets.
>
> To production: VictoriaMetrics Cluster, a Kafka Schema Registry to version the
> MetricMessage contract, and a Redis-backed workflow store so any API replica can
> resume a suspended run — not just the one that started it."

---

## Key technical talking points (if asked)

**On the Mastra suspend-resume pattern:**
> "The workflow doesn't poll — it literally stops executing and persists its state.
> When a human approves, the orchestrator rehydrates the context and resumes from
> step four. That's what makes human-in-the-loop reliable at scale."

**On the confidence score:**
> "0.40 is the base score for a z-score anomaly. Each correlated signal — error logs,
> trace spans — adds weight. We cap it so the agent can never claim certainty it
> doesn't have. An approval at 0.46 means the human knows exactly how thin the evidence is."

**On Kafka fan-out:**
> "One producer, two independent consumer groups on the same topic. VictoriaMetrics
> gets the raw metrics for querying; Elasticsearch gets them for full-text log
> correlation. Neither consumer knows the other exists. Adding a third — say, a
> Slack notifier — is one new consumer group, zero changes to the producer."

**On RBAC:**
> "Three roles: viewer, operator, admin. Viewers see dashboards. Only operators and
> admins can trigger RCA or approve tickets. Enforced at the Fastify route level with
> JWT RS256 — the frontend never has to remember what a viewer can't do."

**On Neptune / AWS migration (if the Metaphactory role comes up):**
> "VictoriaMetrics and Elasticsearch are both swappable — they sit behind interfaces.
> On AWS: VictoriaMetrics → Amazon Managed Prometheus, Elasticsearch → OpenSearch,
> Kafka → MSK. Same application logic."
