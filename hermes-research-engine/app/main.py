"""Hermes Research Engine — FastAPI entrypoint."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

load_dotenv()

from app.agents.orchestrator import OrchestratorAgent
from app.memory.long_term import long_term_memory
from app.memory.episodic import episodic_memory
from app.observability import RequestMetrics, logger
from app.tools.retriever import ingest_document

# In-memory task store (use Redis in prod)
_tasks: Dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.step("startup", "app", "started", model=os.getenv("HERMES_MODEL"))
    yield
    logger.step("shutdown", "app", "stopped")


app = FastAPI(
    title="Hermes Research Engine",
    description="Multi-agent deep research powered by NousResearch Hermes-3",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Schemas ────────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    question: str
    stream: bool = False


class IngestRequest(BaseModel):
    doc_id: str
    text: str
    source: str = ""


# ─── Routes ─────────────────────────────────────────────────────────────────

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def serve_ui():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok", "model": os.getenv("HERMES_MODEL", "NousResearch/Hermes-3-Llama-3.1-8B")}


@app.post("/research")
async def start_research(req: ResearchRequest):
    """
    Start a research task. Returns task_id immediately.
    Poll GET /research/{task_id} or stream from GET /research/{task_id}/stream.
    """
    if not req.question.strip():
        raise HTTPException(400, "question cannot be empty")

    task_id = str(uuid.uuid4())
    metrics = RequestMetrics(trace_id=task_id)
    _tasks[task_id] = {"status": "pending", "question": req.question, "result": None}

    asyncio.create_task(_run_research(task_id, req.question, metrics))
    return {"task_id": task_id, "status": "pending"}


async def _run_research(task_id: str, question: str, metrics: RequestMetrics) -> None:
    _tasks[task_id]["status"] = "running"
    try:
        orch = OrchestratorAgent(trace_id=task_id, metrics=metrics)
        # Run in thread pool to avoid blocking event loop
        result = await asyncio.to_thread(orch.run, question)
        _tasks[task_id] = {
            "status": "completed",
            "question": question,
            "result": result,
            "metrics": metrics.summary(),
        }
    except Exception as exc:
        logger.error(task_id, "app", str(exc))
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["error"] = str(exc)


@app.get("/research/stream")
async def stream_research_direct(question: str = Query(..., description="Research question to stream live")):
    """SSE endpoint for live streaming — pass question as query param."""
    task_id = str(uuid.uuid4())
    metrics = RequestMetrics(trace_id=task_id)

    async def event_generator():
        orch = OrchestratorAgent(trace_id=task_id, metrics=metrics)
        async for event in orch.stream(question):
            yield {"data": event}

    return EventSourceResponse(event_generator())


@app.get("/research/{task_id}")
async def get_research(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return task


@app.get("/research/{task_id}/stream")
async def stream_research(task_id: str = None, question: str = Query(None)):
    """
    SSE endpoint. If task_id exists, streams stored events.
    If question param provided, runs a fresh research session and streams live.
    """
    if question:
        task_id = str(uuid.uuid4())
        metrics = RequestMetrics(trace_id=task_id)

        async def event_generator():
            orch = OrchestratorAgent(trace_id=task_id, metrics=metrics)
            async for event in orch.stream(question):
                yield {"data": event}

        return EventSourceResponse(event_generator())

    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "task not found")

    async def replay():
        while _tasks[task_id]["status"] in ("pending", "running"):
            yield {"data": json.dumps({"type": "status", "msg": _tasks[task_id]["status"]})}
            await asyncio.sleep(1)
        t = _tasks[task_id]
        if t["status"] == "completed":
            yield {"data": json.dumps({"type": "final_report", "content": t["result"]})}
            yield {"data": json.dumps({"type": "metrics", "data": t.get("metrics", {})})}
        else:
            yield {"data": json.dumps({"type": "error", "content": t.get("error", "unknown")})}

    return EventSourceResponse(replay())


@app.post("/memory/ingest")
async def ingest(req: IngestRequest):
    """Add a document to the persistent knowledge base."""
    result = ingest_document(req.doc_id, req.text, req.source)
    return {"message": result}


@app.get("/memory/search")
async def search_memory(q: str = Query(..., description="Search query"), k: int = 5):
    """Semantic search over the knowledge base."""
    results = long_term_memory.search(q, k=k)
    return {"query": q, "results": results}


@app.get("/episodes")
async def list_episodes(n: int = 10):
    """List recent research sessions from episodic memory."""
    return {"episodes": episodic_memory.recent(n)}
