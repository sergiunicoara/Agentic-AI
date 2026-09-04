"""FastAPI application composition.

Kept separate from ``main`` so the wiring (routers, CORS, audit middleware) can
be imported and exercised by tests without pulling in the OTel exporters or the
asyncio server runner.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware.audit_log import AuditLogMiddleware
from app.routers import admin, auth, evals, traces

API_V1 = "/api/v1"

fastapi_app = FastAPI(
    title="Agent Observability Dashboard",
    version="1.0.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

# Exact origin - wildcard + credentials is rejected by browsers and hides
# misconfiguration. Users are JIT-provisioned via OIDC; no seed admin exists.
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
fastapi_app.add_middleware(AuditLogMiddleware)

fastapi_app.include_router(auth.router, prefix=API_V1)
fastapi_app.include_router(traces.router, prefix=API_V1)
fastapi_app.include_router(evals.router, prefix=API_V1)
fastapi_app.include_router(admin.router, prefix=API_V1)


@fastapi_app.get("/api/health")      # unversioned - for load balancers / healthchecks
async def health():
    return {"status": "ok", "api_version": "v1"}


@fastapi_app.get(f"{API_V1}/health")  # versioned alias
async def health_v1():
    return {"status": "ok", "api_version": "v1"}
