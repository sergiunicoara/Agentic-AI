# SmartOps — Interview Demo Script

> **Runtime:** ~12 minutes  
> **Preparation:** 10 minutes before the call  
> **Login:** `admin@smartops.local` / `smartops_dev`  
> **Anomaly cycle:** every ~60 s, random region, lasts 25 s

---

## BEFORE THE CAMERAS ROLL

Do this 10 minutes before the interview. The simulator needs at least 90 seconds of baseline
data in VictoriaMetrics before z-score detection can fire reliably.

> ⚠️ **Every command below must be run from the SmartOps project root.**
> This repo is a monorepo — running `pnpm stack:up` from any other project directory
> (e.g. TradeArena) will fail with `Command "stack:up" not found`.
>
> ```powershell
> cd "C:\Users\Sergiu\Desktop\Projects\Agentic-AI\SmartOps AI observability platform"
> ```
>
> Verify you're in the right place: `cat package.json | findstr stack` should return the
> `docker compose` line.

**Terminal 1 — Infrastructure**
```bash
pnpm stack:up
# wait ~30s for health checks
pnpm db:migrate
```

**Terminal 2 — API**
```bash
pnpm dev:api
```

**Terminal 3 — Web**
```bash
pnpm dev:web
```

**Terminal 4 — Kafka producer** *(keep this visible during the demo)*
```bash
pnpm simulate
```

> ℹ️ On first run the simulator prints `[DB] Seed skipped` — this is harmless. The database
> is already seeded from previous runs. Metrics still publish to Kafka normally.

**Terminal 5 — VictoriaMetrics consumer**
```bash
pnpm simulate:consumer
```

**Terminal 6 — Elasticsearch consumer**
```bash
pnpm simulate:es-consumer
```

> ℹ️ All three must be running for the full pipeline: producer publishes to Kafka,
> consumers fan out to VictoriaMetrics (dashboard) and Elasticsearch (RCA logs).
> The OTel Collector must also be running (`pnpm stack:up`) — logs go directly from
> the simulator to OTel on port 4318, bypassing Kafka.

**Browser tabs to have open:**
| Tab | URL |
|---|---|
| SmartOps | http://localhost:3001 |
| Grafana | http://localhost:3002 |
| API Docs | http://localhost:3000/api/docs |

> ℹ️ **Swagger UI** at `/api/docs` fully renders all endpoints — useful to show during the API
> architecture section. If it appears blank, hard-refresh (Ctrl+Shift+R).

1. Log in at `localhost:3001` → `admin@smartops.local` / `smartops_dev`
2. Confirm live metric values appear on the Dashboard (not dashes).
3. Watch Terminal 4. The simulator prints `[ANOMALY] Injecting CPU spike into {region}` every ~60 s. That's your cue for Scene 4.

---

## COLD OPEN — Setting the Stage (1 min)

*Before touching anything — establish the problem first.*

**YOU SAY:**

> "The problem I wanted to solve is this: in a real production environment, you have dashboards
> showing you hundreds of metrics. Something spikes. An on-call engineer gets paged. They open
> four different tools — Grafana, Kibana, Jaeger, the runbook — and try to manually correlate
> what happened. That takes 20 to 40 minutes on a good night.
>
> SmartOps compresses that loop. The platform detects anomalies automatically, runs a root cause
> analysis by pulling correlated evidence from metrics, logs, and traces simultaneously, and
> surfaces a specific hypothesis for a human to review — not a dashboard to dig through.
> The human approves or rejects. If approved, a ServiceNow ticket is created. The whole flow
> takes about 30 seconds."

---

## SCENE 1 — THE WORLD (2 min)

**ACTION:** Navigate to `http://localhost:3001/dashboard`
Click the **eu-west** region tab, then cycle through **us-east** and **ap-south**.

*On screen: Three region tabs. The active region shows four metric cards — CPU, Memory, P99 Latency,
Error Rate — each with a sparkline updating every 5 seconds. A green "Live" dot in the top right.*

**YOU SAY:**

> "This is the dashboard — real-time telemetry from three regions: EU West, US East, AP South.
> The data you're seeing is coming from VictoriaMetrics, refreshing over a Server-Sent Events
> stream every 2 seconds.
>
> The metric pipeline is: the simulator publishes a structured JSON event to a Kafka topic every
> 5 seconds. A consumer in a separate process reads that topic and remote-writes to VictoriaMetrics.
> A second consumer — different consumer group, completely independent — bulk-indexes the same
> events to Elasticsearch. That's the Kafka fan-out pattern: one producer, multiple sinks,
> neither consumer knows about the other.
>
> I chose VictoriaMetrics over Prometheus for a specific reason. It exposes the exact same
> PromQL API, so any Grafana dashboard works without changes. But VictoriaMetrics gives you
> 10 to 40 times better storage compression and doesn't have the cardinality explosion problem
> that kills production Prometheus instances. One binary, no sidecar.
>
> These four metrics are the Google SRE Golden Signals: latency, traffic, errors, saturation.
> If you can only watch four things in a production system, these are the four. The sparklines
> give you the last 10 minutes of context at a glance — not just the current value.
>
> The transport is SSE — Server-Sent Events. I chose SSE over WebSockets here because the
> data flow is one-directional: server pushes metrics to the browser. SSE is simpler,
> reconnects automatically, and works through HTTP/2 proxies without extra protocol negotiation."

---

## SCENE 2 — THE FOUNDATION (2 min)

**ACTION:** Click **Assets** in the left nav. Scroll briefly. Then click **Alert Rules**.

*On screen: Assets — a table of servers, containers, databases, and load balancers per region,
each with status chips and IP addresses. Alert Rules — a list of threshold-based rules with
severity badges.*

**YOU SAY:**

> "The platform has two detection layers. This first one — Alert Rules — is traditional threshold
> alerting. CPU above 75% fires a warning. CPU above 85% fires a critical. These rules are stored
> in PostgreSQL, managed through Fastify endpoints, and evaluated deterministically. No model
> involved. Fast, auditable, zero false-positive ambiguity.
>
> The second layer is the AI detection you'll see in a moment — z-score anomaly detection that
> catches sustained deviations even when values stay below the absolute threshold. The two layers
> are independent but complementary. Static thresholds catch the obvious fires. Z-score catches
> the slow burns.
>
> The schema here is Drizzle ORM with PostgreSQL. I chose Drizzle over Prisma because Drizzle
> generates raw SQL that you can read and audit. No query magic behind the scenes. The migration
> files are plain SQL — you can run them in psql directly if you need to."

---

## SCENE 3 — THE INCIDENT (up to 60 s wait)

**ACTION:** Click **AI Insights** in the left nav.
Keep one eye on Terminal 4. You're waiting for: `[ANOMALY] Injecting CPU spike into {region}`
**Do NOT click Run AI Scan yet.** Set the scene first.

*On screen: The AI Insights page with a "Run AI Scan" button, a grid of six manual trigger
cards (3 regions × 2 metrics), and an Incident History table.*

**YOU SAY:**

> "The simulator is pushing fresh metrics every 5 seconds to VictoriaMetrics. In a few seconds —
> roughly every 60 — it's going to inject a CPU spike into a random region. CPU will ramp toward
> 95% over about 10 seconds and stay there for 25 seconds before resolving. That spike is what
> I'm waiting for.
>
> The detection logic when I click Run AI Scan: it queries the last 10 minutes of data for each
> metric-region combination — 6 queries in parallel. For each series, it takes the oldest 80% of
> data points as the baseline, computes mean and standard deviation, and asks: is the current
> value more than 2 standard deviations above the mean, and also above the warning threshold?
>
> That's a z-score. No neural network, no fine-tuned model, no training data. Deterministic,
> explainable, reproducible. If CPU is at 92% and the 10-minute baseline mean is 35%, the
> z-score is around 3.8. There's also an absolute backstop: if the latest value exceeds 85%,
> it fires regardless of the z-score — catches spikes that happen in the first minute before
> baseline history builds up."

*⏳ Wait until Terminal 4 shows the anomaly injection. Then wait **5–10 seconds** for the spike
to build. The simulator kicks CPU to 72% immediately on injection, then ramps to 90%+ within
two 5-second ticks — so you don't need to wait long.*

---

## SCENE 4 — THE AI SEES IT FIRST (30 s)

**ACTION:** Click **Run AI Scan**.

*On screen: A red anomaly card with the affected region, the metric name, current value vs.
baseline, and the z-score. A pulsing red dot. A "Trigger RCA" button.*

**YOU SAY:**

> "There it is. CPU in EU West — or whichever region — at 92%, against a 10-minute baseline of
> 35%. Z-score 3.8. Both detection checks passed: absolute threshold exceeded and z-score above 2.
>
> Notice this took under a second. All 6 detection queries ran in parallel using
> Promise.allSettled — one failed query doesn't block the others. This is the fast path:
> deterministic math, no model latency. The LLM only enters the picture in the next step,
> when I ask it to reason about *why* this happened."

> **If no anomaly appears:** "The spike just resolved — the simulator runs them for 25 seconds.
> That's intentionally short to simulate a real burst. Let me trigger the workflow manually
> for the region I saw spike in the terminal." Then click the relevant manual card.

---

## SCENE 5 — THE INVESTIGATION (~30 s loading)

**ACTION:** Click **Trigger RCA** on the anomaly card.
The button shows "Running…". Fill the wait with explanation — you have 25–35 seconds.

**YOU SAY:**

> "What just happened under the hood: the anomaly object — metric, region, host, current value,
> baseline, z-score, timestamp — was sent to a Fastify endpoint that kicks off a Mastra workflow.
> I'm using Mastra rather than LangChain for one specific reason: suspend and resume.
>
> The workflow has four steps. Step one: detect the anomaly. Because I passed the pre-detected
> anomaly directly from the scan results, step one is a no-op — it passes the object forward.
> This was an important optimization. The spike lasts 25 seconds; if the workflow re-queried
> VictoriaMetrics from scratch, there's a real chance the spike would resolve before the
> detection query runs. By passing the already-detected anomaly, we bypass that race condition.
>
> Step two — running right now — is the RCA agent. It's a Claude model call with three tools:
> query VictoriaMetrics for related metrics, search Elasticsearch for error logs in the same
> region and time window, and fetch distributed trace spans from Jaeger. These three tool calls
> run in parallel. The agent then synthesizes all the correlated evidence into a root-cause
> narrative.
>
> Step three, which comes next, suspends the workflow. The workflow literally pauses
> mid-execution, persists its state, and waits for a human to resume it."

---

## SCENE 6 — THE REVEAL (2 min)

*On screen: An approval modal with an RCA summary, a confidence score, correlated evidence,
and 2–3 specific remediation actions. Two buttons: Approve and Reject.*

**YOU SAY:**

> "The workflow suspended. This incident is now written to PostgreSQL with status
> 'pending_approval.' The workflow run ID is persisted — even if the API restarts,
> the workflow can be resumed from exactly where it left off.
>
> *(Read a line or two from the RCA summary)*
>
> The RCA agent looked at the CPU saturation pattern across the 10-minute window, correlated
> it with whatever logs and traces are available, and produced a specific hypothesis.
> In a fully connected environment with real Elasticsearch and Jaeger, you'd see specific
> error messages and slow service spans named here.
>
> Notice the confidence score. The formula is `0.40 base + errorLogs × 0.02 + traceSpans × 0.03`.
> With a fresh stack and no log history you'll see ~40%. After the simulator has run through
> one or two anomaly cycles — typically 2–3 minutes — the Elasticsearch log index has enough
> error-level entries from this region that the score rises to 60–80%.
>
> The RCA agent runs three evidence queries in parallel: VictoriaMetrics for related metrics,
> Elasticsearch for error logs from the same region and time window, and a trace store for
> slow spans. All three run concurrently — if one fails or times out, the workflow continues
> with whatever evidence came back. The confidence score communicates data quality honestly
> to the human reviewer. I'd rather surface a lower score and let a person decide than have
> the system project false certainty."
>
> And the remediation actions — specific to what the agent found. 'SSH into node-01, run
> ps aux sorted by CPU to find the offending process.' That's actionable. Not 'check your
> infrastructure.'"

---

## SCENE 7 — THE DECISION (30 s)

**ACTION:** Click **Approve** in the modal.

*On screen: Modal closes. Incident History table updates — the pending row now shows "ticketed"
with a ServiceNow ticket ID.*

**YOU SAY:**

> "The workflow resumed from the suspend point, ran step four — the ServiceNow agent — and
> the ticket is created. In this demo it's mocked, but the createSnowTicket function is wired
> to the actual ServiceNow REST API. The incident row in PostgreSQL is updated with the
> ticket ID and a resolved timestamp.
>
> The AI never auto-creates tickets. It never takes action without a human in the loop.
> That's not a safety feature tacked on afterwards — it's the core design. Mastra's
> suspend-resume primitive is what makes that pattern possible without polling, without
> callbacks, and without state machines hand-coded in the application layer."

---

## SCENE 8 — THE EVIDENCE (1 min)

**ACTION:** Switch to `localhost:3002`. Login: **admin** / **smartops_dev**
Navigate to **Dashboards → SmartOps Golden Signals**.

*On screen: Time series panels for CPU, memory, P99, error rate. The spike from a few
minutes ago is clearly visible as a peak in the CPU panel.*

**YOU SAY:**

> "Here's the same spike from the infrastructure side. Grafana is reading from VictoriaMetrics
> directly over PromQL — the same data source the SmartOps anomaly detector queries.
> Both views are consuming the same ground truth.
>
> This is what an on-call engineer would see in a traditional setup: a spike on a dashboard.
> Then they'd open Kibana, open Jaeger, cross-reference timestamps manually. SmartOps
> collapses that loop to one button click and 30 seconds of AI-assisted triage."

---

## SCENE 9 — THE WRAP (2 min)

**ACTION:** Switch back to `localhost:3001/dashboard`.

**YOU SAY:**

> "To summarize what you just saw: Fastify 4 API on port 3000, Next.js 14 App Router on 3001,
> VictoriaMetrics for time-series on 8428, PostgreSQL on 5433 via Docker. The AI agents live
> in a shared workspace package — @smartops/ai-agents — consumed by the API as a module.
> Mastra manages workflow state in SQLite for local dev; in production that would be a
> PostgreSQL-backed workflow store.
>
> The auth layer is JWT with RS256, RBAC enforced at the Fastify preHandler level. The AI
> workflow endpoints require the operator or admin role — a viewer account can see incidents
> but can't trigger workflows or approve them.
>
> The metric pipeline is already Kafka-backed — the simulator publishes JSON events to a topic,
> two consumer groups fan out independently to VictoriaMetrics and Elasticsearch. Adding a third
> sink is a new consumer file; the producer doesn't change.
>
> To take this to production: VictoriaMetrics Cluster for horizontal metric scaling, a dedicated
> Elasticsearch cluster for log correlation at volume, a Kafka Schema Registry to enforce the
> MetricMessage contract between producers and consumers, and a Redis-backed workflow store
> instead of the in-process Mastra SQLite runner — so any API replica can resume a suspended
> workflow, not just the one that started it."

---

## ANTICIPATED QUESTIONS

**"Why Mastra and not LangChain?"**

> "The specific capability I needed — a workflow that literally suspends mid-execution and
> resumes from a different HTTP request — isn't a first-class primitive in LangChain.
> The TypeScript SDK is a port of the Python library and lags behind. In Mastra, suspend-resume
> is the core execution model. That single feature determines the entire human-in-the-loop
> architecture, so it wasn't a marginal difference."

---

**"Why Fastify instead of Express?"**

> "Fastify validates request bodies against JSON Schema at the route level. Invalid payloads
> never reach handler code. Express requires you to bolt that on separately. Fastify also
> benchmarks at roughly twice Express's throughput. For a metrics ingestion API that handles
> bursts of telemetry, that matters."

---

**"Why z-score and not a machine learning model?"**

> "No training data required, no model drift, and it's auditable. I can tell you exactly why
> any given anomaly fired — here's the mean, here's the standard deviation, here's the z-score.
> With a neural network I'd need labeled historical incidents, a training pipeline, and I still
> couldn't explain individual decisions cleanly. Z-score is the right tool for the detection
> layer. The LLM handles the reasoning step, where statistical explainability doesn't apply anyway."

---

**"How would you scale this to production?"**

> "Kafka is already in the stack — metric events are published once and two consumer groups
> fan out independently. Adding more consumers doesn't touch the producer. For the rest:
> VictoriaMetrics Cluster for horizontal metric storage, a dedicated Elasticsearch cluster,
> and a Redis-backed Mastra workflow store so any API replica can resume a suspended run.
> The Fastify API and Next.js frontend are already stateless — they scale horizontally as-is."

---

**"Is it safe to have AI touching production incidents?"**

> "The AI touches nothing in production. It reads telemetry and produces a hypothesis. A human
> with the operator or admin role approves every action. The Mastra suspend-resume pattern
> enforces this at the workflow level — it's not a UI convention that can be bypassed, it's
> the execution model. I'd call that more auditable than most existing on-call tooling."

---

**"What would you do differently if you started over?"**

> "I'd add a Kafka Schema Registry from day one. Right now the MetricMessage contract between
> the simulator and both consumers is a TypeScript interface — it's enforced at compile time
> but nothing catches a breaking change at runtime if a consumer is on an older build. A
> Schema Registry with Avro would make schema evolution explicit and versioned.
>
> I'd also wire up OpenTelemetry spans around each agent.generate() call. The platform is
> built to observe infrastructure — but the AI layer itself is a black box. Tracing LLM
> latency and tool call counts with the same OTel stack that traces everything else would
> be a natural fit and close an obvious irony."

---

**"Why is the confidence score only 40%?" / "What raises it?"**

> "The confidence formula is `0.40 + errorLogs × 0.02 + traceSpans × 0.03`. Base is 40% —
> metric evidence only. Each error-level log from the same region and time window adds 2 points;
> each correlated trace span adds 3.
>
> The demo is wired to push this above 40%. The OTel Collector uses ECS field mapping so
> simulator logs land with the field names the RCA agent queries — `message`, `log.level`,
> `labels.region`. The second Kafka consumer bulk-indexes the same metric events to
> Elasticsearch. Once the simulator has run through one or two anomaly cycles, the RCA agent
> finds 10–20 error-level logs in the 12-minute correlation window and confidence rises
> to 60–80%.
>
> The design principle: confidence is honest signal, not marketing. A score below 75% tells
> the human reviewer the AI is working from limited evidence and they should verify independently.
> That transparency is intentional — I'd rather surface a low-confidence alert than let the
> system project false certainty."

---

## TROUBLESHOOTING

Common issues and how to handle them during the demo.

**Dashboard shows no data / values are all zero**

The metric pipeline requires three processes: the Kafka producer (`pnpm simulate`), the
VictoriaMetrics consumer (`pnpm simulate:consumer`), and the infrastructure stack (`pnpm stack:up`).
If the consumer isn't running, metrics are published to Kafka but never reach VictoriaMetrics,
so the dashboard shows nothing. Start all three and wait ~10 seconds for the consumer to
catch up on any buffered messages.

**Dashboard values lag behind the simulator terminal**

The dashboard polls VictoriaMetrics every 2 seconds via SSE; the simulator pushes every
5 seconds. There is up to 2 seconds of lag — normal. If you see a much larger gap
(e.g., 46% in terminal, 72% on screen), the API server needs a restart:

```bash
# Ctrl+C the pnpm dev:api terminal, then:
pnpm dev:api
```

**"[DB] Seed skipped" in the simulator output**

Harmless. The database is already seeded. Metrics still push to VictoriaMetrics normally.

**Anomaly appears in terminal but dashboard doesn't spike**

The simulator kicks CPU to 72% immediately on injection. The dashboard should show the
spike within 2–5 seconds. If it doesn't, confirm `pnpm dev:api` is running (SSE requires
the API to be up) and that you're logged in (the SSE stream requires a valid JWT).

**Anomaly resolved but dashboard still shows high CPU**

Expected — the CPU drifts back toward baseline (~35%) over 30–40 seconds after resolution.
The `[ANOMALY] Resolved` message means the injection stopped, not that CPU snapped back
instantly. Watch the dashboard — it will visibly decrease every few seconds.

**Incident appears in history with no summary ("—")**

Happens when you trigger the RCA workflow before the CPU spike has ramped up (e.g., at
40%). Claude received a weak anomaly signal, returned an incomplete RCA, and the row was
written with null fields. Fixed in current code — the API now only writes the incident
row when Claude produces a non-empty summary. Old rows are harmless; ignore them.

**How to browse the database**

Port 5433 is PostgreSQL's binary protocol — it is not an HTTP interface.
To browse tables in a web UI:
```bash
pnpm db:studio   # opens https://local.drizzle.studio
```
Or via psql:
```bash
psql postgresql://smartops:smartops_dev@localhost:5433/smartops
```

---

## STOP

```bash
pnpm stack:down
```
