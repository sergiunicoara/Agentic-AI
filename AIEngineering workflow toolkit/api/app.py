"""
FastAPI Web Server — AI Engineering Workflow Toolkit

Exposes:
  POST /api/reviews          Submit a diff for review
  GET  /api/reviews          List review history
  GET  /api/reviews/{id}     Get review detail + disposition
  GET  /api/stats            Aggregate stats
  GET  /api/eval/latest      Latest eval regression result
  GET  /api/eval/history     Last N eval runs (for trend sparkline)
  WS   /ws/{review_id}       Live pipeline progress stream
  GET  /                     Serve React SPA (from ui/dist)
"""
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.database import (
    init_db,
    create_review,
    complete_review,
    fail_review,
    list_reviews,
    get_review,
    review_stats,
)

_REPO_ROOT = Path(__file__).parent.parent

app = FastAPI(title="AI Engineering Workflow Toolkit", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory progress bus ────────────────────────────────────────────────────
_event_log: dict[str, list[dict]] = {}
_subscribers: dict[str, list[WebSocket]] = {}


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup() -> None:
    init_db()


# ── REST endpoints ────────────────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    diff: str
    title: str = ""
    source: str = "manual"   # "manual" | "hook"


@app.post("/api/reviews")
async def submit_review(req: ReviewRequest, background_tasks: BackgroundTasks):
    if not req.diff.strip():
        raise HTTPException(status_code=400, detail="diff must not be empty")

    review_id = str(uuid.uuid4())
    source = req.source if req.source in ("manual", "hook") else "manual"
    title = req.title.strip() or f"Review {review_id[:8]}"
    created_at = datetime.now(timezone.utc).isoformat()

    create_review(review_id, title, req.diff, created_at, source=source)
    _event_log[review_id] = []
    _subscribers[review_id] = []

    background_tasks.add_task(_run_pipeline, review_id, req.diff)

    return {
        "id": review_id,
        "status": "running",
        "title": title,
        "source": source,
        "created_at": created_at,
    }


@app.get("/api/reviews")
async def get_reviews():
    return list_reviews()


@app.get("/api/reviews/{review_id}")
async def get_review_detail(review_id: str):
    review = get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@app.get("/api/stats")
async def get_stats():
    return review_stats()


@app.get("/api/eval/latest")
async def get_eval_latest():
    entries = _load_eval_log()
    return entries[-1] if entries else None


@app.get("/api/eval/history")
async def get_eval_history(n: int = 10):
    """Return the last N eval run summaries for trend visualization."""
    entries = _load_eval_log()
    return entries[-n:] if len(entries) >= n else entries


def _load_eval_log() -> list[dict]:
    log_path = _REPO_ROOT / "eval" / "regression_log.jsonl"
    if not log_path.exists():
        return []
    lines = [
        ln.strip()
        for ln in log_path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and '"cases_run"' in ln  # filter suppressed-finding events
    ]
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return result


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/{review_id}")
async def ws_progress(websocket: WebSocket, review_id: str):
    await websocket.accept()

    for event in _event_log.get(review_id, []):
        try:
            await websocket.send_json(event)
        except Exception:
            return

    past = _event_log.get(review_id, [])
    if past and past[-1].get("type") in ("complete", "error"):
        await websocket.close()
        return

    _subscribers.setdefault(review_id, []).append(websocket)

    try:
        while True:
            await asyncio.sleep(25)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        subs = _subscribers.get(review_id, [])
        try:
            subs.remove(websocket)
        except ValueError:
            pass


# ── Pipeline execution ────────────────────────────────────────────────────────

async def _broadcast(review_id: str, event: dict) -> None:
    _event_log.setdefault(review_id, []).append(event)
    dead: list[WebSocket] = []
    for ws in list(_subscribers.get(review_id, [])):
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            _subscribers[review_id].remove(ws)
        except ValueError:
            pass


async def _run_pipeline(review_id: str, diff: str) -> None:
    from orchestrator.agent import OrchestratorAgent
    from review_agent.agent import ReviewAgent

    async def on_progress(event: dict) -> None:
        await _broadcast(review_id, event)

    pipeline_start = time.monotonic()

    try:
        orchestrator = OrchestratorAgent()
        merged = await orchestrator.run(diff, _REPO_ROOT, on_progress=on_progress)

        reviewer = ReviewAgent()
        disposition = await reviewer.review(merged, on_progress=on_progress)

        elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)

        await _broadcast(review_id, {
            "type": "complete",
            "review_id": review_id,
            "verdict": disposition.get("verdict"),
            "elapsed_ms": elapsed_ms,
        })

        complete_review(review_id, disposition, elapsed_ms=elapsed_ms)

    except Exception as exc:
        err = str(exc)
        await _broadcast(review_id, {"type": "error", "message": err})
        fail_review(review_id, err)

    finally:
        await asyncio.sleep(300)
        _event_log.pop(review_id, None)
        _subscribers.pop(review_id, None)


# ── React SPA ─────────────────────────────────────────────────────────────────

_UI_DIST = _REPO_ROOT / "ui" / "dist"

if _UI_DIST.exists():
    _ASSETS = _UI_DIST / "assets"
    if _ASSETS.exists():
        app.mount("/assets", StaticFiles(directory=str(_ASSETS)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        target = _UI_DIST / full_path
        if target.exists() and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_UI_DIST / "index.html"))
