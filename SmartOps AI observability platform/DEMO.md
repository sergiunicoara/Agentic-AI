# SmartOps — Demo Script

> **Video runtime:** ~4 minutes
> **Interview runtime:** ~12 minutes (add Q&A section below)
> **Login:** `admin@smartops.local` / `smartops_dev`

---

## SETUP (10 min before recording)

```powershell
cd "C:\Users\Sergiu\Desktop\Projects\Agentic-AI\SmartOps AI observability platform"
```

| Terminal | Command |
|---|---|
| 1 | `pnpm stack:up && pnpm db:migrate` |
| 2 | `pnpm dev:api` |
| 3 | `pnpm dev:web` |
| 4 | `pnpm simulate` |
| 5 | `pnpm simulate:consumer` |
| 6 | `pnpm simulate:es-consumer` |
| 7 | `pnpm simulate:traces` |

**Wait 2–3 minutes** before recording — Terminal 7 auto-detects CPU anomalies from VictoriaMetrics and injects slow/error spans in the affected region, pushing confidence above 60%. Watch Terminal 7 for `[ANOMALY: eu-west]` alongside Terminal 4's `[ANOMALY] Injecting CPU spike`.

Browser tabs:
- `http://localhost:3001` — SmartOps web
- `http://localhost:3002` — Grafana

---

## COLD OPEN (20 s)

> "On-call engineer gets paged. They open Grafana, Kibana, Jaeger, the runbook — and spend
> 20 minutes manually correlating what happened. SmartOps compresses that to 30 seconds:
> detect, investigate, create a ticket — with a human approving every step."

---

## SCENE 1 — LIVE DASHBOARD (45 s)

**ACTION:** Show `localhost:3001/dashboard`. Click through all three region tabs.

> "Three regions, five golden signals each — CPU, Memory, P99 Latency, Error Rate, Requests per
> second. Data comes from VictoriaMetrics via a Kafka fan-out pipeline: one producer publishes
> JSON events every 5 seconds, two independent consumer groups read the same topic — one writes
> to VictoriaMetrics, one bulk-indexes to Elasticsearch. The browser receives updates over
> Server-Sent Events every 2 seconds."

---

## SCENE 2 — THE SPIKE (30 s)

**ACTION:** Keep Terminal 4 visible. Wait for `[ANOMALY] Injecting CPU spike`. Then show
the Grafana dashboard (`localhost:3002`) — the CPU panel should spike within 10 seconds.

> "The simulator just injected a CPU anomaly. Watch Grafana — same VictoriaMetrics data source
> the AI queries. This is what a traditional on-call engineer sees: a spike. Now watch what
> SmartOps does with it."

---

## SCENE 3 — AI DETECTS IT (30 s)

**ACTION:** Go to `localhost:3001` → **AI Insights** → click **Run AI Scan**.

> "Six detection queries run in parallel — three regions, two metrics each. For each series
> it computes a z-score against the last 10 minutes of baseline. CPU at 92%, baseline mean 35%,
> z-score 3.8 — anomaly confirmed. Under a second, no model involved, purely deterministic math."

*On screen: red anomaly card with region, metric, current value vs baseline, z-score.*

**ACTION:** Click **Trigger RCA**.

> "Now the LLM enters. A Mastra workflow kicks off — it queries VictoriaMetrics for correlated
> metrics, Elasticsearch for error logs, and a trace store for slow spans, all in parallel.
> Then Claude synthesizes the evidence into a root-cause hypothesis."

---

## SCENE 4 — THE DECISION (45 s)

*On screen: approval modal with RCA summary, confidence score, correlated evidence,
remediation actions.*

> "The workflow suspended. It literally paused mid-execution, persisted state to SQLite, and
> is waiting for a human. This isn't a UI convention — Mastra's suspend-resume is the execution
> model. The confidence score is `0.40 base + error logs × 0.02 + trace spans × 0.03` — honest
> signal about how much evidence the agent found.
>
> *(Read one line from the RCA summary)*
>
> Specific remediation actions — not 'check your infrastructure.' Let's approve it."

**ACTION:** Click **Approve**.

> "Workflow resumes, step four fires — the ServiceNow agent creates a ticket. Incident row in
> PostgreSQL updates to 'ticketed' with the ticket ID. The AI touched nothing in production.
> It read, reasoned, and waited. A human with operator role made the call."

*On screen: incident history row showing status = ticketed, INC number.*

---

## SCENE 5 — GRAFANA EVIDENCE (20 s)

**ACTION:** Switch to `localhost:3002` → Golden Signals dashboard.

> "Here's the same spike from the infrastructure side — the peak that triggered everything.
> In a traditional setup this is where the investigation starts. SmartOps already closed it."

---

## WRAP (30 s)

> "Stack: Fastify 4 API, Next.js 14, VictoriaMetrics, Elasticsearch, Kafka KRaft,
> PostgreSQL, Mastra AI workflows with Claude. Auth is JWT RS256, RBAC enforced at the
> route level — viewers can't trigger workflows or approve tickets.
>
> To production: VictoriaMetrics Cluster, a Kafka Schema Registry to version the
> MetricMessage contract, and a Redis-backed workflow store so any API replica can resume
> a suspended run — not just the one that started it."

---

## ANTICIPATED QUESTIONS (interviews only)

**"Why Mastra and not LangChain?"**

> "The specific capability I needed — a workflow that suspends mid-execution and resumes
> from a different HTTP request — isn't a first-class primitive in LangChain. In Mastra,
> suspend-resume is the core execution model. That single feature determines the entire
> human-in-the-loop architecture."

---

**"Why z-score and not an ML model?"**

> "No training data, no model drift, fully auditable. I can tell you exactly why any anomaly
> fired — here's the mean, the standard deviation, the z-score. The LLM handles reasoning,
> where statistical explainability doesn't apply. Right tool for each layer."

---

**"Why VictoriaMetrics over Prometheus?"**

> "Same PromQL API — any Grafana dashboard works without changes. But VictoriaMetrics gives
> 10–40× better storage compression and no cardinality explosion at scale. One binary, no
> sidecar, drop-in replacement."

---

**"How would you scale this?"**

> "Kafka is already in the stack — adding a third sink is a new consumer file, producer
> doesn't change. VictoriaMetrics Cluster for horizontal metric storage, dedicated
> Elasticsearch cluster, Redis-backed Mastra workflow store. The API and frontend are
> stateless — they scale horizontally as-is."

---

**"Is it safe to have AI touching production incidents?"**

> "The AI touches nothing in production. It reads telemetry and produces a hypothesis.
> Mastra's suspend-resume enforces the human gate at the execution level — not a UI
> convention that can be bypassed."

---

**"What would you do differently?"**

> "Kafka Schema Registry from day one — the MetricMessage contract between producer and
> consumers is a TypeScript interface right now, enforced at compile time but not at runtime.
> And OTel spans around each agent.generate() call — the platform observes infrastructure
> but the AI layer itself is a black box. Tracing LLM latency with the same OTel stack
> would close an obvious irony."

---

**"Why is confidence only 40%?"**

> "Formula: `0.40 base + errorLogs × 0.02 + traceSpans × 0.03`. With a fresh stack there
> are no logs yet. After 2–3 anomaly cycles Elasticsearch has error-level entries and
> confidence rises to 60–80%. The score is honest signal — I'd rather surface low confidence
> than project false certainty."

---

## TROUBLESHOOTING

**Dashboard shows dashes** — confirm all 6 terminals are running. Consumer must be up for
metrics to reach VictoriaMetrics.

**Values lag the terminal** — normal, up to 7s (5s simulator + 2s SSE). Much larger gap:
restart `pnpm dev:api`.

**No anomaly appears in AI Scan** — spike lasted 25s and resolved before you clicked.
Use a manual trigger card (region × metric grid below the Run button).

**Confidence stuck at 40%** — simulator hasn't run long enough. Wait for 2–3 anomaly cycles
(~3 min) so ES has indexed error logs.

---

## STOP

```bash
pnpm stack:down
```
