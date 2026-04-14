from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from opentelemetry import trace
from pydantic import BaseModel

from .agent import agent_turn
from .voice import voice_bench_handler, voice_handler
from .critic_agent import get_critic_session_summary, validate_turn
from .mcp import call_mcp_tool, list_mcp_tools
from .models import ChatRequest, ChatResponse, State
from .quality import StepKind, Trajectory
from .telemetry.logging import configure_logging
from .telemetry.tracing import configure_tracer

logger = logging.getLogger(__name__)

SERVICE_NAME = "recruiter-agent"

app = FastAPI(title="Recruiter Agent API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Startup: wire OpenTelemetry tracing + structured logging
# ------------------------------------------------------------------

@app.on_event("startup")
async def startup_event() -> None:
    configure_logging(SERVICE_NAME)
    configure_tracer(
        SERVICE_NAME,
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )
    logger.info("Recruiter Agent started | service=%s", SERVICE_NAME)


# ------------------------------------------------------------------
# Frontend serving
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@app.get("/", include_in_schema=False)
async def serve_frontend_root():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise RuntimeError(f"Frontend index.html not found at {index_path}")
    return FileResponse(index_path)


@app.get("/{path:path}", include_in_schema=False)
async def serve_frontend_assets(path: str):
    file_path = FRONTEND_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")


# ------------------------------------------------------------------
# /chat — main recruiter agent entrypoint
# ------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint with full trajectory logging and OTel tracing.

    Every turn emits:
    - An OTel span with session/role/criteria attributes
    - A structured trajectory log (user step + agent step with timestamps)
    """
    session_id = req.session_id or "default-session"
    tracer = trace.get_tracer(SERVICE_NAME)

    with tracer.start_as_current_span("chat.turn") as span:
        span.set_attribute("session_id", session_id)
        span.set_attribute("source", req.source or "")
        span.set_attribute("message_length", len(req.message))

        # Restore state
        if req.state:
            incoming = req.state if isinstance(req.state, dict) else dict(req.state)
            state = State(
                source=incoming.get("source"),
                role=incoming.get("role"),
                criteria=incoming.get("criteria", []),
                memory=incoming.get("memory", []),
                extra=incoming.get("extra", {}),
            )
        else:
            state = State(source=req.source)

        # Trajectory: log user turn
        trajectory = Trajectory(session_id=session_id)
        trajectory.add(
            StepKind.user,
            req.message,
            meta={"source": req.source, "session_id": session_id},
        )

        with tracer.start_as_current_span("agent.turn"):
            result = agent_turn(state, req.message)

        if result is None:
            raise RuntimeError("agent_turn returned None")

        reply = result.get("reply")
        new_state = result.get("state")

        if reply is None:
            raise RuntimeError("agent_turn returned dict without 'reply'")

        span.set_attribute("role", new_state.role or "")
        span.set_attribute("reply_length", len(reply))

        # Trajectory: log agent turn
        trajectory.add(
            StepKind.agent,
            reply,
            meta={
                "role": new_state.role,
                "criteria": new_state.criteria,
                "memory_events": len(new_state.memory),
            },
        )

        # Emit full trajectory to structured logs
        logger.info(
            "agent_trajectory | session=%s role=%s turns=%d",
            session_id,
            new_state.role or "unknown",
            trajectory.to_dict()["turn_count"],
            extra={"json_fields": trajectory.to_dict()},
        )

    safe_state = {
        "source": new_state.source,
        "role": new_state.role,
        "criteria": new_state.criteria,
        "memory": new_state.memory,
        "extra": new_state.extra,
    }

    return ChatResponse(
        reply=reply,
        state=safe_state,
        session_id=session_id,
    )


# ------------------------------------------------------------------
# /mcp/tools — discover available MCP tools
# ------------------------------------------------------------------

@app.get("/mcp/tools")
async def mcp_list_tools_endpoint() -> Dict[str, Any]:
    """
    Returns the registry of MCP-style tools with JSON input/output schemas.
    External agents use this for tool discovery before making /mcp/call requests.
    """
    return {"tools": list_mcp_tools()}


# ------------------------------------------------------------------
# /mcp/call — dispatch a named tool call
# ------------------------------------------------------------------

class MCPCallRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}


@app.post("/mcp/call")
async def mcp_call_endpoint(req: MCPCallRequest) -> Dict[str, Any]:
    """
    MCP-inspired Agent-to-Agent dispatch endpoint.

    Accepts a named tool call with JSON arguments and returns a structured result.
    Used by the eval runner and critic agent for automated validation.
    """
    tracer = trace.get_tracer(SERVICE_NAME)
    with tracer.start_as_current_span("mcp.call") as span:
        span.set_attribute("tool", req.tool)
        try:
            result = call_mcp_tool(req.tool, req.arguments)
            return {"tool": req.tool, "result": result}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            logger.exception("MCP tool call failed: tool=%s error=%s", req.tool, exc)
            raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------
# /a2a/validate — Critic Agent A2A validation endpoint
# ------------------------------------------------------------------

class A2AValidateRequest(BaseModel):
    user_message: str
    agent_reply: str
    role: Optional[str] = None
    criteria: List[str] = []
    session_id: str = "default"


@app.post("/a2a/validate")
async def a2a_validate_endpoint(req: A2AValidateRequest) -> Dict[str, Any]:
    """
    Agent-to-Agent validation endpoint.

    Invokes the Critic Agent, which calls the LLM judge via the MCP tool
    interface and returns a structured verdict (PASS/FAIL) with:
    - Multi-metric scores (faithfulness, relevancy, factuality)
    - Concrete recommended actions
    - Running session aggregate metrics
    """
    tracer = trace.get_tracer(SERVICE_NAME)
    with tracer.start_as_current_span("a2a.validate") as span:
        span.set_attribute("session_id", req.session_id)
        span.set_attribute("role", req.role or "")

        result = validate_turn(
            user_message=req.user_message,
            agent_reply=req.agent_reply,
            role=req.role,
            criteria=req.criteria,
            session_id=req.session_id,
        )

        span.set_attribute("verdict", result.get("verdict", ""))
        span.set_attribute("score", result.get("score", 0.0))

    return result


# ------------------------------------------------------------------
# /a2a/summary — Critic session aggregate metrics
# ------------------------------------------------------------------

@app.websocket("/voice")
async def voice_endpoint(ws: WebSocket, session_id: str = "default"):
    await voice_handler(ws, session_id)


@app.websocket("/voice/bench")
async def voice_bench_endpoint(ws: WebSocket, session_id: str = "bench"):
    await voice_bench_handler(ws, session_id)


@app.get("/a2a/summary/{session_id}")
async def a2a_summary_endpoint(session_id: str) -> Dict[str, Any]:
    """
    Returns aggregate validation metrics for a given critic session.
    Useful for tracking quality trends across a full recruiter conversation.
    """
    return get_critic_session_summary(session_id)
