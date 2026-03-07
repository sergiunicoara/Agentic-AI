# Agent Observability Dashboard

A production-ready developer tooling platform for monitoring and debugging agentic workflows in real-time.

## Architecture

```
Browser (React + TS)
  ├── gRPC-Web ──► Envoy :8080 ──► gRPC Server :50051 ┐
  └── REST     ──► Envoy :8080 ──► FastAPI     :8000  ┘ (same Python process)

Data layer:
  Postgres :5432  → persistent trace/span/eval/user storage
  Redis    :6379  → JWT revocation, session state

Observability:
  OTel Collector :4317 → receives OTLP traces from backend

SDK (pip install):
  agent_observability → AgentTracer, AsyncSpan, OTel bridge
```

## Quick Start

```bash
# 1. Copy environment config
cp .env.example .env

# 2. Start everything
docker compose up --build

# 3. Open the dashboard
open http://localhost:5173
# Login: admin@example.com / password

# 4. Generate proto stubs for SDK (required before running the example)
pip install grpcio-tools
python scripts/generate_proto.py

# 5. Install the SDK and run the example agent
pip install -e ./sdk
python sdk/examples/simple_agent.py
# → Watch live traces appear in the dashboard
```

## Services

| Service | URL | Purpose |
|---|---|---|
| Frontend | http://localhost:5173 | React dashboard |
| Envoy | http://localhost:8080 | gRPC-Web + REST proxy |
| Backend REST | http://localhost:8000/api/v1/docs | FastAPI Swagger |
| gRPC | localhost:50051 | SDK event intake |
| OTel Collector | localhost:4317 | Telemetry receiver |
| Envoy Admin | http://localhost:9901 | Envoy metrics |

## Project Structure

```
agent-observability/
├── proto/v1/                 # Protobuf definitions — package agent_events.v1
├── backend/
│   ├── app/
│   │   ├── main.py           # asyncio entry-point: FastAPI + gRPC
│   │   ├── grpc_server.py    # AgentEventServicer (EmitEvent, SubscribeEvents)
│   │   ├── models/           # SQLAlchemy models (traces, spans, evals, users)
│   │   ├── routers/          # FastAPI routers (auth, traces, evals, admin)
│   │   ├── services/         # event_bus, trace_service, auth_service, otel_setup
│   │   └── middleware/       # Audit log middleware
│   └── alembic/              # Database migrations
├── frontend/
│   └── src/
│       ├── components/       # TraceViewer, TokenUsageChart, LatencyChart, TaskOutcomes
│       ├── hooks/            # useEventStream (gRPC-Web), useAuth
│       ├── store/            # Zustand trace store
│       └── api/              # grpcClient, restClient
├── sdk/
│   ├── agent_observability/  # AgentTracer, AsyncSpan, GrpcEmitter, OtelBridge
│   └── examples/simple_agent.py
├── envoy/envoy.yaml          # gRPC-Web transcoding proxy
├── otel/otel-collector-config.yaml
└── docker-compose.yml
```

## REST API

**Current version:** `v1`

Base URL: `http://localhost:8080/api/v1` (via Envoy) or `http://localhost:8000/api/v1` (direct)

Swagger UI: `http://localhost:8000/api/v1/docs`

| Method | Path | Role | Description |
|---|---|---|---|
| POST | /auth/login | — | Get JWT token |
| POST | /auth/logout | any | Revoke token |
| GET | /traces | viewer+ | List agent traces |
| GET | /traces/{id} | viewer+ | Get trace with spans |
| GET | /evals | viewer+ | List eval runs |
| POST | /evals | developer+ | Create eval run |
| POST | /evals/{id}/results | developer+ | Add eval result |
| GET | /admin/users | admin | List users |
| POST | /admin/users | admin | Create user |
| PATCH | /admin/users/{id}/role | admin | Update user role |
| GET | /admin/audit | admin | Audit log |

Unversioned: `GET /api/health` — for load balancer health checks (always available regardless of API version).

## gRPC API

**Current version:** `v1` — package `agent_events.v1`

Proto source: `proto/v1/agent_events.proto`

```protobuf
package agent_events.v1;

service AgentEventService {
  rpc EmitEvent(AgentEvent) returns (EmitResponse);                   // SDK → backend
  rpc SubscribeEvents(SubscribeRequest) returns (stream AgentEvent);  // frontend → backend
}
```

Envoy routes `agent_events.v1.AgentEventService/*` → gRPC backend :50051.

## SDK Usage

```python
from agent_observability import AgentTracer

async def main():
    async with AgentTracer(server="localhost:50051", agent_name="my-agent") as tracer:
        async with tracer.trace("task-001") as trace:
            async with trace.span("llm_call", model="claude-sonnet-4-6") as span:
                result = await call_llm(prompt)
                span.record_tokens(input=512, output=128)

            async with trace.span("tool_call") as span:
                span.set_attribute("tool", "web_search")
                data = await search(query)

            trace.set_outcome("success")
```

## RBAC

| Role | Permissions |
|---|---|
| `viewer` | Read traces, read evals, subscribe to live stream |
| `developer` | All viewer permissions + create/delete eval runs |
| `admin` | All developer permissions + user management + audit log |

## Proto Generation

After changing `proto/v1/agent_events.proto`:

```bash
# Python stubs (backend + SDK)
python scripts/generate_proto.py

# JS stubs (frontend) — requires protoc-gen-grpc-web
npm run gen:proto --prefix frontend
```

The Docker build runs proto generation automatically.

## Development (without Docker)

```bash
# Start Postgres and Redis
docker compose up postgres redis otel-collector -d

# Backend
cd backend
pip install -r requirements.txt
python scripts/generate_proto.py  # from repo root
python -m app.main

# Frontend
cd frontend
npm install
npm run dev
```
