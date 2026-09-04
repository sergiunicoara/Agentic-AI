"""gRPC emitter: sends AgentEvent messages to the backend."""

import sys
from pathlib import Path
from typing import Optional

import grpc

# Allow running from a source checkout without installing the package: the
# generated stubs live under backend/ and are imported as app.generated.*
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if _BACKEND_ROOT.is_dir() and str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from app.generated import agent_events_pb2, agent_events_pb2_grpc
except ImportError as exc:
    raise ImportError(
        "Could not import generated proto stubs. "
        "Run `python scripts/generate_proto.py` from the repo root first."
    ) from exc


def _tls_credentials(
    tls_ca_file: str,
    client_cert_file: str,
    client_key_file: str,
):
    """Create mTLS credentials for a production ingestion gateway."""
    if not tls_ca_file:
        return None
    if bool(client_cert_file) != bool(client_key_file):
        raise ValueError("client_cert_file and client_key_file must be configured together")

    root_certificates = Path(tls_ca_file).read_bytes()
    certificate_chain = Path(client_cert_file).read_bytes() if client_cert_file else None
    private_key = Path(client_key_file).read_bytes() if client_key_file else None
    return grpc.ssl_channel_credentials(
        root_certificates=root_certificates,
        private_key=private_key,
        certificate_chain=certificate_chain,
    )


class GrpcEmitter:
    """Thread-safe gRPC client that sends events to the observability backend."""

    def __init__(
        self,
        server: str = "localhost:50051",
        api_key: str = "",
        tls_ca_file: str = "",
        client_cert_file: str = "",
        client_key_file: str = "",
    ):
        if not api_key:
            raise ValueError("api_key is required for telemetry ingestion")
        credentials = _tls_credentials(tls_ca_file, client_cert_file, client_key_file)
        self._channel = (
            grpc.secure_channel(server, credentials)
            if credentials
            else grpc.insecure_channel(server)
        )
        self._stub = agent_events_pb2_grpc.AgentEventServiceStub(self._channel)
        self._metadata = (("x-api-key", api_key),)

    def emit(self, **kwargs) -> bool:
        event = agent_events_pb2.AgentEvent(**kwargs)
        try:
            response = self._stub.EmitEvent(event, timeout=5.0, metadata=self._metadata)
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

    def __init__(
        self,
        server: str = "localhost:50051",
        api_key: str = "",
        tls_ca_file: str = "",
        client_cert_file: str = "",
        client_key_file: str = "",
    ):
        import grpc.aio as aio

        if not api_key:
            raise ValueError("api_key is required for telemetry ingestion")
        self._channel: Optional[aio.Channel] = None
        self._server = server
        self._tls_credentials = _tls_credentials(
            tls_ca_file, client_cert_file, client_key_file
        )
        self._stub: Optional[agent_events_pb2_grpc.AgentEventServiceStub] = None
        self._metadata = (("x-api-key", api_key),)

    async def connect(self) -> None:
        import grpc.aio as aio

        self._channel = (
            aio.secure_channel(self._server, self._tls_credentials)
            if self._tls_credentials
            else aio.insecure_channel(self._server)
        )
        self._stub = agent_events_pb2_grpc.AgentEventServiceStub(self._channel)

    async def emit(self, **kwargs) -> bool:
        event = agent_events_pb2.AgentEvent(**kwargs)
        try:
            response = await self._stub.EmitEvent(event, timeout=5.0, metadata=self._metadata)
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
