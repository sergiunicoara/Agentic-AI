# SmartOps Demo Guide

## Prerequisites

- Node.js ≥ 20, pnpm ≥ 9
- Docker Desktop running

## Setup (one-time)

```bash
pnpm install
cp .env.example .env
# SERVICENOW_MOCK=true is already set — no real SN instance needed
```

## Run (4 terminals)

**Terminal 1 — infrastructure**
```bash
pnpm stack:up
# wait ~30s for health checks, then:
pnpm db:migrate
```

**Terminal 2 — API**
```bash
pnpm dev:api
```

**Terminal 3 — web dashboard**
```bash
pnpm dev:web
```

**Terminal 4 — traffic simulator**
```bash
pnpm simulate
```

## Open in browser

| URL | What it is |
|---|---|
| http://localhost:3001 | SmartOps dashboard |
| http://localhost:3002 | Grafana (admin / `smartops_dev`) |
| http://localhost:3000/api/docs | API Swagger docs |

**Login:** `admin@smartops.local` — any password

## What to show

1. **Dashboard** — live metrics for 3 regions (EU West, US East, AP South), updating every 5s
2. **Anomaly** — every ~60s the simulator spikes CPU in a random region; watch the region tab turn red
3. **AI Insights → Run AI Scan** — detects the anomaly with z-score
4. **Trigger RCA** — correlates metrics + logs + traces, shows confidence score and suggested actions
5. **Approve & Create Ticket** — creates a mock ServiceNow incident
6. **Grafana** — Golden Signals dashboard shows the same spike from the infra side
7. **Assets** — pre-seeded servers, containers, databases, load balancers per region

## Stop

```bash
pnpm stack:down
```
