"""Entry point: runs FastAPI (uvicorn) and gRPC server in the same asyncio event loop."""

import asyncio

import uvicorn

from app.api import fastapi_app
from app.config import settings
from app.grpc_server import start_grpc_server
from app.services.otel_setup import setup_otel


async def main() -> None:
    setup_otel(fastapi_app)
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
