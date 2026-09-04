# Graph Report - SmartOps AI observability platform  (2026-09-04)

## Corpus Check
- Corpus is ~35,396 words - fits in a single context window. You may not need a graph.

## Summary
- 414 nodes · 701 edges · 31 communities (24 shown, 7 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 25 edges (avg confidence: 0.9)
- Token cost: 82,104 measured · rest unmeasured (see "Build Method & Honest Accounting" below — NOT zero)

## Community Hubs (Navigation)
- Architecture & Design Rationale
- API Schema & Data Models
- Mastra AI Agent Suite
- AI Insights Frontend
- Shared Types & RBAC
- Infra Simulator (Kafka Producer)
- SSE Metrics Streaming
- API Package Dependencies
- Elasticsearch Consumer
- Web App Dependencies
- VictoriaMetrics Consumer
- AI Agent Dependencies
- Web Middleware & Auth
- Web App Layout
- Next.js Config
- Next.js Env Types
- Tailwind Config
- E2E Package Manifest
- Scripts Package Manifest

## God Nodes (most connected - your core abstractions)
1. `README.md — SmartOps architecture, tech stack, architectural considerations` - 23 edges
2. `VictoriaMetrics (time-series metrics store, PromQL-compatible)` - 17 edges
3. `Elasticsearch 8 (logs, metrics, traces store, :9200)` - 14 edges
4. `@smartops/ai-agents — four Mastra agents (anomalyDetector, rootCauseAnalyzer, forecastingAgent, servicenowAgent)` - 13 edges
5. `DEMO.md — SmartOps demo script and anticipated questions` - 12 edges
6. `Fastify 4 API (:3000) — REST routes, RBAC, SSE` - 12 edges
7. `buildApp()` - 10 edges
8. `Docker Compose — full SmartOps local observability stack` - 9 edges
9. `Helm values.yaml — SmartOps Kubernetes deployment configuration` - 9 edges
10. `Next.js 14 web dashboard (:3001)` - 9 edges

## Surprising Connections (you probably didn't know these)
- `Video script — SmartOps AI-assisted incident response demo` --semantically_similar_to--> `DEMO.md — SmartOps demo script and anticipated questions`  [INFERRED] [semantically similar]
  docs/video-script-smartops-demo.md → DEMO.md
- `Helm Template: VictoriaMetrics StatefulSet + Service` --references--> `VictoriaMetrics (time-series metrics store, PromQL-compatible)`  [EXTRACTED]
  infra/helm/smartops/templates/victoriametrics.yaml → docs/adr/003-victoriametrics-over-prometheus.md
- `Helm Template: API Deployment + HPA + PDB` --references--> `Fastify 4 API (:3000) — REST routes, RBAC, SSE`  [EXTRACTED]
  infra/helm/smartops/templates/api-deployment.yaml → README.md
- `Helm Template: Web Deployment + Service` --references--> `Next.js 14 web dashboard (:3001)`  [EXTRACTED]
  infra/helm/smartops/templates/web-deployment.yaml → README.md
- `CLAUDE.md — SmartOps agent workflow instructions` --conceptually_related_to--> `SmartOps AI Observability Platform`  [INFERRED]
  CLAUDE.md → README.md

## Import Cycles
- None detected.

## Communities (31 total, 7 thin omitted)

### Community 0 - "Architecture & Design Rationale"
Cohesion: 0.08
Nodes (69): CLAUDE.md — SmartOps agent workflow instructions, Agent workflow conventions (plan mode, subagents, verification, lessons), @smartops/ai-agents — four Mastra agents (anomalyDetector, rootCauseAnalyzer, forecastingAgent, servicenowAgent), alertToTicket workflow (detect → RCA → approve → ticket), Alertmanager (prom/alertmanager v0.27.0, :9093), Anthropic Claude via @ai-sdk/anthropic (claude-sonnet-4-6, claude-haiku-4-5), AWS migration path (AMP / OpenSearch / MSK), Dead-letter topic smartops.metrics.dlq (planned) (+61 more)

### Community 1 - "API Schema & Data Models"
Cohesion: 0.07
Nodes (42): alertRules, alertRulesRelations, alertSeverityEnum, assets, assetsRelations, assetStatusEnum, assetTypeEnum, auditLog (+34 more)

### Community 2 - "Mastra AI Agent Suite"
Cohesion: 0.08
Nodes (41): mastra, ABSOLUTE_THRESHOLDS, anomalyDetector, detectAnomalies(), forecastingAgent, ForecastResult, forecastSaturation(), linearTrend() (+33 more)

### Community 3 - "AI Insights Frontend"
Cohesion: 0.05
Nodes (33): AIPage(), AnomalyEvent, fetcher(), Incident, REGIONS, WATCHED, WorkflowResult, DashboardPage() (+25 more)

### Community 4 - "Shared Types & RBAC"
Cohesion: 0.06
Nodes (29): fastify, FastifyInstance, AlertsPage(), CONDITIONS, fetcher(), SEVERITIES, ASSET_TYPES, AssetsPage() (+21 more)

### Community 5 - "Infra Simulator (Kafka Producer)"
Cohesion: 0.14
Nodes (22): clamp(), drift(), esClient, generateTraceSpans(), jitter(), kafka, LOG_TEMPLATES, loop() (+14 more)

### Community 6 - "SSE Metrics Streaming"
Cohesion: 0.17
Nodes (17): metricsRoutes(), broadcast(), REGIONS, startBroadcast(), subscribe(), Subscriber, subscribers, cache (+9 more)

### Community 7 - "API Package Dependencies"
Cohesion: 0.13
Nodes (14): bcryptjs, drizzle-kit, drizzle-orm, fastify, @fastify/cors, @fastify/helmet, @fastify/jwt, fastify-plugin (+6 more)

### Community 8 - "Elasticsearch Consumer"
Cohesion: 0.22
Nodes (13): buffer, consumer, dailyIndex(), esClient, flush(), kafka, main(), MetricDoc (+5 more)

### Community 9 - "Web App Dependencies"
Cohesion: 0.18
Nodes (10): autoprefixer, clsx, postcss, react, react-dom, recharts, swr, tailwindcss (+2 more)

### Community 10 - "VictoriaMetrics Consumer"
Cohesion: 0.31
Nodes (7): consumer, kafka, main(), MetricMessage, pushToVictoriaMetrics(), toPrometheusText(), waitForGroupCoordinator()

### Community 12 - "AI Agent Dependencies"
Cohesion: 0.33
Nodes (5): @ai-sdk/anthropic, @mastra/core, @mastra/memory, @mastra/pg, vitest

## Knowledge Gaps
- **135 isolated node(s):** `@ai-sdk/anthropic`, `@mastra/core`, `@mastra/memory`, `@mastra/pg`, `vitest` (+130 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `api` connect `AI Insights Frontend` to `Shared Types & RBAC`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Why does `Config` connect `API Schema & Data Models` to `SSE Metrics Streaming`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Why does `detectAnomalies()` connect `Mastra AI Agent Suite` to `API Schema & Data Models`?**
  _High betweenness centrality (0.008) - this node is a cross-community bridge._
- **What connects `@ai-sdk/anthropic`, `@mastra/core`, `@mastra/memory` to the rest of the system?**
  _135 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Architecture & Design Rationale` be split into smaller, more focused modules?**
  _Cohesion score 0.0784313725490196 - nodes in this community are weakly interconnected._
- **Should `API Schema & Data Models` be split into smaller, more focused modules?**
  _Cohesion score 0.06545879602571596 - nodes in this community are weakly interconnected._
- **Should `Mastra AI Agent Suite` be split into smaller, more focused modules?**
  _Cohesion score 0.07676767676767676 - nodes in this community are weakly interconnected._

---

## Build Method & Honest Accounting

**Token cost:** 82,104 tokens measured (chunk 1, 22 docs/configs) + unmeasured
cost for chunk 2. chunk 2 (9 files: CLAUDE.md, DEMO.md, README.md, ADR-002, ADR-004, scaling.md, video-script, docker-compose.yml, values.yaml) errored after writing its output but before reporting usage — its token cost is unmeasured, not zero. The first build of this graph recorded
`0 input / 0 output` for BOTH chunks, which was wrong — the counters were never
backfilled from the subagent results. This report shows what was actually measured
and is explicit that the rest is unknown rather than silently reporting zero.

**Noise filter applied.** This graph is NOT the raw graphify output. Nodes sourced from
build configuration were removed before clustering, because they dominated the raw graph
without carrying architectural meaning (the raw build's top "god nodes" included
`compilerOptions` and `scripts` — JSON keys, not abstractions):

- dropped: all nodes from `tsconfig.json` and `turbo.json`
- dropped: `package.json` metadata scalars (name/version/private/scripts/engines) and
  per-file dependency entry nodes
- kept: the `package.json` file nodes and deduped external-package nodes; dependency
  edges were **lifted** to run `<package.json> --imports--> <external package>` so no
  relationship was lost
- kept: every source-code node and every semantic/concept node
- file-level nodes are preserved even when isolated (a file with no extractable symbols
  is still a true fact about the repo)

Verified after filtering: 0 edges pointing at removed nodes, 0 self-loops.

**Known limits of this graph:**
- Clustering on a repo this size largely recovers *file boundaries*, not emergent
  concepts. Treat community labels as navigation aids, not discovered architecture.
- `contains` and `imports` edges are structural; only `calls`, `indirect_call`,
  `rationale_for`, `conceptually_related_to` and `shares_data_with` express
  non-obvious relationships.
- The corpus is ~35k words and fits in a single context window (see Corpus Check
  above). The graph is a navigation convenience here, not a necessity.
- **The "Communities" section below undercounts two communities and omits one
  entirely** (graphify's own report renderer, not the filtering in this rebuild).
  `graph.json` is correct and was verified directly: community 10 has 9 nodes
  ("VictoriaMetrics Consumer"), community 11 has 7 nodes (Playwright `login()`
  helpers across 3 e2e specs, omitted below), and community 12 has 6 nodes
  ("AI Agent Dependencies"). Trust `graph.json` / `graph.html` / `graphify query`
  over the prose counts in the Communities section for these three.
