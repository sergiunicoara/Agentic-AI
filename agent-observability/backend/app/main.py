"""Entry point: runs FastAPI (uvicorn) and gRPC server in the same asyncio event loop."""

import asyncio
import uuid

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import AsyncSessionLocal, init_db
from app.grpc_server import start_grpc_server
from app.middleware.audit_log import AuditLogMiddleware
from app.models.user import User
from app.routers import admin, auth, evals, traces
from app.services.auth_service import hash_password
from app.services.otel_setup import setup_otel

API_V1 = "/api/v1"

fastapi_app = FastAPI(
    title="Agent Observability Dashboard",
    version="1.0.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
fastapi_app.add_middleware(AuditLogMiddleware)

fastapi_app.include_router(auth.router, prefix=API_V1)
fastapi_app.include_router(traces.router, prefix=API_V1)
fastapi_app.include_router(evals.router, prefix=API_V1)
fastapi_app.include_router(admin.router, prefix=API_V1)


@fastapi_app.get("/api/health")      # unversioned — for load balancers / healthchecks
async def health():
    return {"status": "ok", "api_version": "v1"}


@fastapi_app.get(f"{API_V1}/health") # versioned alias
async def health_v1():
    return {"status": "ok", "api_version": "v1"}


async def seed_admin() -> None:
    """Create the default admin user if not already present."""
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.email == settings.seed_admin_email)
        )
        if result.scalar_one_or_none() is None:
            admin_user = User(
                id=str(uuid.uuid4()),
                email=settings.seed_admin_email,
                hashed_password=hash_password(settings.seed_admin_password),
                role="admin",
            )
            db.add(admin_user)
            await db.commit()
            print(f"Seeded admin user: {settings.seed_admin_email}")


async def main() -> None:
    setup_otel(fastapi_app)
    await init_db()
    await seed_admin()

    grpc_server = await start_grpc_server(port=settings.grpc_port)

    uv_config = uvicorn.Config(
        app=fastapi_app,
        host="0.0.0.0",
        port=settings.rest_port,
        loop="none",
        log_level="info",
    )
    uv_server = uvicorn.Server(config=uv_config)

    await asyncio.gather(
        grpc_server.wait_for_termination(),
        uv_server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
