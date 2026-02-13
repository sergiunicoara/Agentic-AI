from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .agent import agent_turn
from .models import ChatRequest, ChatResponse, State


app = FastAPI()

# CORS so frontend (GitHub Pages, local dev, Cloud Run) can call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can restrict this later
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
    index_path = FRONTEND_DIR / "index.html"
    return FileResponse(index_path)


# ------------------------------------------------------------------
# /chat endpoint – main recruiter agent entrypoint
# ------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint used by the frontend.

    - If req.state is present, we restore it into a State object.
    - Otherwise we create a fresh State (first message of the session).
    - We call agent_turn(state, message) and serialize the updated state.
    """

    # Restore state safely, *only* from JSON-safe fields
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

    result = agent_turn(state, req.message)
    # result must be a dict like: { "reply": "...", "state": State }

    if result is None:
        raise RuntimeError("agent_turn returned None")

    reply = result.get("reply")
    new_state = result.get("state")

    if reply is None:
        raise RuntimeError("agent_turn returned dict without 'reply'")

    # Only return JSON-safe fields back to the frontend
    safe_state = {
        "source": new_state.source,
        "role": new_state.role,
        "criteria": new_state.criteria,
        "memory": new_state.memory,
        "extra": new_state.extra,
    }

    session_id = req.session_id or "default-session"

    return ChatResponse(
        reply=reply,
        state=safe_state,
        session_id=session_id,
    )
