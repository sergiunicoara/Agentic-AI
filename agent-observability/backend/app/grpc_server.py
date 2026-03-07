"""gRPC server implementing AgentEventService.

EmitEvent  → called by SDK-instrumented agents (push path)
SubscribeEvents → called by the frontend to receive a live stream (pull path)
"""

import asyncio
import uuid

import grpc
from grpc import aio as grpc_aio

from app.generated import agent_events_pb2, agent_events_pb2_grpc
from app.services.auth_service import decode_token, is_revoked
from app.services.event_bus import event_bus
from app.services.trace_service import handle_event


class AgentEventServicer(agent_events_pb2_grpc.AgentEventServiceServicer):
    async def EmitEvent(
        self,
        request: agent_events_pb2.AgentEvent,
        context: grpc_aio.ServicerContext,
    ) -> agent_events_pb2.EmitResponse:
        try:
            await handle_event(request)
            return agent_events_pb2.EmitResponse(accepted=True)
        except Exception as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def SubscribeEvents(
        self,
        request: agent_events_pb2.SubscribeRequest,
        context: grpc_aio.ServicerContext,
    ):
        # Authenticate via session_token in the request (gRPC metadata auth
        # is handled separately for emitters; frontend passes JWT here).
        token = request.session_token
        try:
            payload = decode_token(token)
            if await is_revoked(payload.get("jti", "")):
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Token revoked")
                return
        except Exception:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")
            return

        sub_id, queue = event_bus.subscribe()
        try:
            while not context.cancelled():
                try:
                    event: agent_events_pb2.AgentEvent = await asyncio.wait_for(
                        queue.get(), timeout=30.0
                    )
                except asyncio.TimeoutError:
                    # Send a keepalive (empty event) so the connection stays alive
                    yield agent_events_pb2.AgentEvent()
                    continue

                if _matches_filter(event, request):
                    yield event
        finally:
            event_bus.unsubscribe(sub_id)


def _matches_filter(
    event: agent_events_pb2.AgentEvent,
    req: agent_events_pb2.SubscribeRequest,
) -> bool:
    if req.filter_agents and event.agent_name not in req.filter_agents:
        return False
    if req.filter_trace_id and event.trace_id != req.filter_trace_id:
        return False
    return True


async def start_grpc_server(port: int = 50051) -> grpc_aio.Server:
    server = grpc_aio.server(
        options=[
            ("grpc.max_send_message_length", 4 * 1024 * 1024),
            ("grpc.max_receive_message_length", 4 * 1024 * 1024),
        ]
    )
    agent_events_pb2_grpc.add_AgentEventServiceServicer_to_server(
        AgentEventServicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    print(f"gRPC server listening on :{port}")
    return server
