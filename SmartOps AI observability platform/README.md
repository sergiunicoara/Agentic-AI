# SmartOps AI Observability Platform

A full-stack AI-powered observability platform built as a pnpm + Turborepo monorepo. It unifies metrics, logs, and traces into a single dashboard, and uses Mastra AI agents to detect anomalies, forecast trends, run root-cause analysis, and auto-create ServiceNow tickets.

---

## Architecture

```
apps/
  api/          Fastify REST API — auth, RBAC, metrics/logs/traces routes, SSE streaming
  web/          Next.js 14 dashboard — real-time charts, alert rules, asset registry, AI chat
  ai-agents/    Mastra agent suite — anomaly detection, forecasting, RCA, ServiceNow workflow

packages/
  shared-types/ Zod schemas and TypeScript types shared across api + web

infra/
  docker/       Docker Compose — brings up the full observability stack locally
  helm/         Helm chart for Kubernetes deployment
  grafana/      Provisioned dashboards (golden signals, log explorer, asset audit)
  otel/         OTel Collector config (OTLP → VictoriaMetrics + Elasticsearch)
  vector/       Vector log pipeline (Docker logs → Elasticsearch)
  victoria/     VictoriaMetrics scrape config + VMAlert rules

e2e/            Playwright end-to-end test suite
scripts/        Infrastructure simulator (generates synthetic metrics/logs/traces)
```

## Tech Stack

| Layer | Technology |
|---|---|
| API | Fastify 4, Drizzle ORM, PostgreSQL 16, JWT |
| Frontend | Next.js 14, Tailwind CSS, Recharts, SWR |
| AI Agents | Mastra, Anthropic Claude (`@ai-sdk/anthropic`) |
| Metrics | VictoriaMetrics + VMAlert + Alertmanager |
| Logs & Traces | Elasticsearch 8 + Vector pipeline |
| Telemetry | OpenTelemetry Collector (OTLP gRPC :4317 / HTTP :4318) |
| Dashboards | Grafana 10 (provisioned) |
| Monorepo | pnpm workspaces + Turborepo |
| E2E | Playwright |
| K8s | Helm chart (`infra/helm/smartops/`) |

---

## Getting Started

### Prerequisites

- Node.js ≥ 20
- pnpm ≥ 9 (`npm i -g pnpm`)
- Docker + Docker Compose

### 1. Install dependencies

```bash
pnpm install
```

### 2. Configure environment

```bash
cp .env.example .env
cp apps/web/.env.local.example apps/web/.env.local
# Fill in ANTHROPIC_API_KEY and any other values
```

### 3. Start the infrastructure stack

```bash
pnpm stack:up
```

This starts VictoriaMetrics, VMAlert, Alertmanager, Elasticsearch, PostgreSQL, Grafana, OTel Collector, and Vector.

### 4. Run database migrations

```bash
pnpm db:migrate
```

### 5. Start the apps

```bash
# All apps in parallel
pnpm dev

# Or individually
pnpm dev:api   # Fastify API on :3000
pnpm dev:web   # Next.js dashboard on :3001
```

### 6. (Optional) Simulate infrastructure traffic

```bash
pnpm simulate
```

Generates synthetic metrics, logs, and traces against the local stack.

---

## Service URLs

| Service | URL |
|---|---|
| API | http://localhost:3000 |
| API Swagger docs | http://localhost:3000/api/docs |
| Web dashboard | http://localhost:3001 |
| Grafana | http://localhost:3002 (admin / `smartops_dev`) |
| VictoriaMetrics | http://localhost:8428 |
| Elasticsearch | http://localhost:9200 |
| Alertmanager | http://localhost:9093 |
| OTel Collector (HTTP) | http://localhost:4318 |
| Vector API | http://localhost:8686 |

---

## AI Agents

The `@smartops/ai-agents` package exposes four Mastra agents:

| Agent | Description |
|---|---|
| `anomalyDetector` | Detects statistical anomalies in VictoriaMetrics time-series data |
| `forecastingAgent` | Forecasts metric trends using historical data |
| `rootCauseAnalyzer` | Correlates metrics, logs, and traces to identify root causes |
| `servicenowAgent` | Creates and updates ServiceNow incidents from alert payloads |

The `alertToTicket` Mastra workflow chains anomaly detection → RCA → ServiceNow ticket creation as a human-in-the-loop flow.

---

## Scripts

```bash
pnpm dev              # Run all apps in watch mode
pnpm build            # Build all packages
pnpm typecheck        # TypeScript check across all packages
pnpm lint             # Lint all packages
pnpm simulate         # Run infrastructure traffic simulator
pnpm db:generate      # Generate Drizzle migrations
pnpm db:migrate       # Apply migrations
pnpm stack:up         # Start Docker Compose infrastructure
pnpm stack:down       # Stop infrastructure
pnpm stack:logs       # Tail infrastructure logs
```

---

## E2E Tests

```bash
cd e2e
pnpm install
pnpm exec playwright test
```

Covers auth, dashboard, assets, and AI agent flows.

---

## Architecture Decision Records

- [ADR-001: pnpm Workspaces + Turborepo](docs/adr/001-monorepo-with-turborepo.md)
- [ADR-002: Mastra HITL Workflow](docs/adr/002-mastra-hitl-workflow.md)
- [ADR-003: VictoriaMetrics over Prometheus](docs/adr/003-victoriametrics-over-prometheus.md)
- [ADR-004: SSE for Real-time Metrics](docs/adr/004-sse-for-realtime-metrics.md)

## Runbooks

- [Incident Response](docs/runbooks/incident-response.md)
- [Scaling](docs/runbooks/scaling.md)
