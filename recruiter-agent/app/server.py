from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .agent import agent_turn
from .mcp import call_mcp_tool, list_mcp_tools
from .models import ChatRequest, ChatResponse, State
from .quality import StepKind, Trajectory

logger = logging.getLogger(__name__)

app = FastAPI(title="Recruiter Agent API", version="1.0.0")

# CORS so frontend (GitHub Pages, local dev, Cloud Run) can call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Frontend serving (index.html from /frontend)
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
# /chat — main recruiter agent entrypoint (with trajectory logging)
# ------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint used by the frontend.

    Every turn is recorded into a Trajectory (user → agent steps)
    and emitted to structured logs for observability.
    """
    session_id = req.session_id or "default-session"

    # Restore state safely from JSON-safe fields
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

    # --- Trajectory: log user turn ---
    trajectory = Trajectory(session_id=session_id)
    trajectory.add(
        StepKind.user,
        req.message,
        meta={"source": req.source, "session_id": session_id},
    )

    result = agent_turn(state, req.message)

    if result is None:
        raise RuntimeError("agent_turn returned None")

    reply = result.get("reply")
    new_state = result.get("state")

    if reply is None:
        raise RuntimeError("agent_turn returned dict without 'reply'")

    # --- Trajectory: log agent turn ---
    trajectory.add(
        StepKind.agent,
        reply,
        meta={
            "role": new_state.role,
            "criteria": new_state.criteria,
            "memory_events": len(new_state.memory),
        },
    )

    # Emit full trajectory to structured logs (Cloud Logging picks this up)
    logger.info(
        "agent_trajectory",
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
# /mcp/tools — list available MCP-style tools
# ------------------------------------------------------------------

@app.get("/mcp/tools")
async def mcp_list_tools_endpoint() -> Dict[str, Any]:
    """
    Returns the registry of available MCP-style tools with their JSON schemas.
    External agents can discover and call these tools programmatically.
    """
    return {"tools": list_mcp_tools()}


# ------------------------------------------------------------------
# /mcp/call — dispatch a named tool call (A2A interface)
# ------------------------------------------------------------------

class MCPCallRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}


@app.post("/mcp/call")
async def mcp_call_endpoint(req: MCPCallRequest) -> Dict[str, Any]:
    """
    MCP-inspired Agent-to-Agent endpoint.

    Accepts a named tool call with JSON arguments and returns a structured result.
    Supported tools: cv_rag_query, best_projects_for_role,
                     ats_summary_and_email, judge_recruiter_turn.
    """
    try:
        result = call_mcp_tool(req.tool, req.arguments)
        return {"tool": req.tool, "result": result}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("MCP tool call failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
