"""gRPC emitter: sends AgentEvent messages to the backend."""

import sys
from pathlib import Path
from typing import Optional

import grpc

# Allow running from the sdk/ directory without installing the package
_SDK_ROOT = Path(__file__).parent.parent.parent
_BACKEND_GENERATED = _SDK_ROOT / "backend" / "app" / "generated"
if str(_BACKEND_GENERATED) not in sys.path:
    sys.path.insert(0, str(_BACKEND_GENERATED.parent.parent))  # adds backend/

try:
    from app.generated import agent_events_pb2, agent_events_pb2_grpc
except ImportError as exc:
    raise ImportError(
        "Could not import generated proto stubs. "
        "Run `python scripts/generate_proto.py` from the repo root first."
    ) from exc


class GrpcEmitter:
    """Thread-safe gRPC client that sends events to the observability backend."""

    def __init__(self, server: str = "localhost:50051"):
        self._channel = grpc.insecure_channel(server)
        self._stub = agent_events_pb2_grpc.AgentEventServiceStub(self._channel)

    def emit(self, **kwargs) -> bool:
        event = agent_events_pb2.AgentEvent(**kwargs)
        try:
            response = self._stub.EmitEvent(event, timeout=5.0)
            return response.accepted
        except grpc.RpcError:
            return False

    def close(self) -> None:
        self._channel.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class AsyncGrpcEmitter:
    """Async gRPC emitter using grpcio-aio."""

    def __init__(self, server: str = "localhost:50051"):
        import grpc.aio as aio

        self._channel: Optional[aio.Channel] = None
        self._server = server
        self._stub: Optional[agent_events_pb2_grpc.AgentEventServiceStub] = None

    async def connect(self) -> None:
        import grpc.aio as aio

        self._channel = aio.insecure_channel(self._server)
        self._stub = agent_events_pb2_grpc.AgentEventServiceStub(self._channel)

    async def emit(self, **kwargs) -> bool:
        event = agent_events_pb2.AgentEvent(**kwargs)
        try:
            response = await self._stub.EmitEvent(event, timeout=5.0)
            return response.accepted
        except grpc.RpcError:
            return False

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.close()
