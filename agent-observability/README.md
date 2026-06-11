# Agent Observability Dashboard

A production-ready developer tooling platform for monitoring and debugging agentic workflows in real-time.

## Architecture

```
Browser (React + TS)
  ├── gRPC-Web ──► Envoy :8080 ──► gRPC Server :50051 ┐
  └── REST     ──► Envoy :8080 ──► FastAPI     :8000  ┘ (same Python process)

Auth:
  OIDC (Authorization Code Flow + PKCE) → any standard provider (Google, Keycloak, Auth0)
  Internal session tokens (JWT, HS256) issued after OIDC validation

Data layer:
  Postgres :5432  → persistent trace/span/eval/user/audit storage
  Redis    :6379  → OIDC state/PKCE verifiers, session token revocation

Observability:
  OTel Collector :4317 → receives OTLP traces from backend

SDK (pip install):
  agent_observability → AgentTracer, AsyncSpan, OTel bridge
```

## Quick Start

```bash
# 1. Copy environment config and fill in OIDC credentials
cp .env.example .env

# 2. Start everything
docker compose up --build

# 3. Apply DB migrations (first run only)
docker compose exec backend sh -c "export PYTHONPATH=/app && cd /app && alembic stamp 0001 && alembic upgrade head"
# If columns already exist (app created them via init_db): stamp directly
# docker compose exec backend sh -c "export PYTHONPATH=/app && cd /app && alembic stamp 0002"

# 4. Open the dashboard
open http://localhost:5173
# Click "Sign in with OIDC" → authenticates via your configured provider
```

## OIDC Configuration

Add to `.env.example` (or `.env`):

```env
OIDC_ISSUER_URL=https://accounts.google.com          # or Keycloak/Auth0 issuer
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret                # leave empty for public clients
OIDC_REDIRECT_URI=http://localhost:5173/auth/callback
EMIT_API_KEY=dev-emit-key                            # gRPC EmitEvent auth — change in prod
FRONTEND_ORIGIN=http://localhost:5173                # exact CORS origin
```

**Google OAuth2:** Create credentials at console.cloud.google.com → OAuth 2.0 Client ID → Web application. Add `http://localhost:5173/auth/callback` as an authorised redirect URI.

**Keycloak (local):** Add to `docker-compose.yml`, create a realm + client, set issuer to `http://host.docker.internal:8081/realms/<realm>`.

Users are **JIT-provisioned** on first login (default role: `viewer`). Promote via SQL or the Admin panel.

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
│   │   ├── services/         # event_bus, trace_service, auth_service, oidc_service, abac
│   │   └── middleware/       # Audit log middleware
│   └── alembic/              # Database migrations
├── frontend/
│   └── src/
│       ├── components/       # TraceViewer, TokenUsageChart, LatencyChart, TaskOutcomes
│       ├── hooks/            # useEventStream (gRPC-Web), useAuth (OIDC PKCE)
│       ├── pages/            # LoginPage, OIDCCallbackPage, TracesPage, EvalsPage, AdminPage
│       ├── store/            # Zustand trace store
│       └── api/              # grpcClient, restClient (PKCE helpers)
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

| Method | Path | Access | Description |
|---|---|---|---|
| GET | /auth/authorize | — | Initiate OIDC flow (rate-limited 10/min/IP) |
| POST | /auth/callback | — | Exchange OIDC code + PKCE verifier for session token |
| POST | /auth/logout | any | Revoke session token |
| GET | /traces | viewer+ | List agent traces (metadata only — treated as public) |
| GET | /traces/{id} | viewer+ | Trace detail — spans filtered by clearance_level |
| GET | /evals | viewer+ | List eval runs |
| POST | /evals | developer+ | Create eval run |
| POST | /evals/{id}/results | developer+ | Add eval result |
| GET | /admin/users | admin | List users |
| POST | /admin/users | admin | Pre-provision OIDC user (email, role, clearance, dept) |
| PATCH | /admin/users/{id} | admin | Update attributes — revokes the user's active sessions |
| POST | /admin/users/{id}/revoke-sessions | admin | Force-logout a user |
| GET | /admin/audit | admin | Audit log |

Unversioned: `GET /api/health` — for load balancer health checks.

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

**Auth:** `EmitEvent` requires the `EMIT_API_KEY` value in `x-api-key` gRPC metadata
(the SDK sends it automatically). `SubscribeEvents` requires a valid session token
and applies the same per-span ABAC filtering as the REST trace-detail endpoint —
the live stream cannot leak spans the user couldn't read from history.

## ABAC (Attribute-Based Access Control)

Span access is controlled by attributes on the subject (user) and resource (span):

**Subject attributes** (stored in user record, embedded in session token):

| Attribute | Values | Effect |
|---|---|---|
| `role` | `viewer` / `developer` / `admin` | Base permissions |
| `clearance_level` | `0` / `1` / `2` | Data sensitivity access |
| `department` | e.g. `security` | Bypass clearance for confidential |

**Resource attributes** (set on spans via `attributes` dict):

| Attribute | Values | Required clearance |
|---|---|---|
| `data_sensitivity` | `public` | 0 (all users) |
| `data_sensitivity` | `internal` | 1 (developer+) |
| `data_sensitivity` | `confidential` | 2 (admin or security dept) |
| `owner_email` | user email | owner always reads own spans |

**Tagging spans from the SDK:**

```python
async with trace.span("llm_call") as span:
    span.set_attribute("data_sensitivity", "confidential")
    span.set_attribute("owner_email", "user@example.com")
```

**Promoting a user:** `PATCH /api/v1/admin/users/{id}` with `{"role": "admin", "clearance_level": 2}` —
this also revokes the user's active sessions, so the change applies on their next login
instead of waiting out the 60-minute token lifetime. (Direct SQL works too, but then
call `POST /admin/users/{id}/revoke-sessions` yourself.)

## SDK Usage

```python
from agent_observability import AgentTracer

async def main():
    async with AgentTracer(server="localhost:50051", agent_name="my-agent") as tracer:
        async with tracer.trace("task-001") as trace:
            async with trace.span("llm_call", model="claude-sonnet-4-6") as span:
                result = await call_llm(prompt)
                span.record_tokens(input=512, output=128)
                span.set_attribute("data_sensitivity", "internal")

            async with trace.span("tool_call") as span:
                span.set_attribute("tool", "web_search")
                data = await search(query)

            trace.set_outcome("success")
```

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
