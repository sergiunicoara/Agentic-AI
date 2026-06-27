"""
Sentinel A2A Server.

Exposes Sentinel as an A2A-compatible HTTP endpoint.
Other agents can:
1. Discover Sentinel at GET /.well-known/agent-card.json
2. Submit review tasks at POST /a2a/review
3. Poll for results at GET /a2a/review/{task_id}

Run with: python -m sentinel.a2a.server
"""
import sys
import uuid
import asyncio
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sentinel.a2a.agent_card import AGENT_CARD
from sentinel.pipeline import run_sentinel
from sentinel.redteam.runner import run_red_team

app = FastAPI(title="Sentinel A2A Server")

# In-memory task store (sufficient for demo)
tasks: dict = {}


class ReviewRequest(BaseModel):
    target_path: str
    include_red_team: bool = False
    task_id: str | None = None


class A2ATask(BaseModel):
    id: str
    status: str  # pending, running, completed, failed
    target: str
    created_at: str
    completed_at: str | None = None
    result: dict | None = None


@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    """A2A discovery endpoint — returns Sentinel's agent card."""
    return JSONResponse(AGENT_CARD)


@app.post("/a2a/review")
async def submit_review(request: ReviewRequest, background_tasks: BackgroundTasks):
    """
    Submit a security review task.
    Returns immediately with a task_id for polling.
    """
    task_id = request.task_id or f"task_{uuid.uuid4().hex[:8]}"

    task = {
        "id": task_id,
        "status": "pending",
        "target": request.target_path,
        "include_red_team": request.include_red_team,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "result": None,
    }
    tasks[task_id] = task

    background_tasks.add_task(
        _run_review_task, task_id, request.target_path, request.include_red_team
    )

    return {"task_id": task_id, "status": "pending", "message": "Review started"}


@app.get("/a2a/review/{task_id}")
async def get_review_result(task_id: str):
    """Poll for review task results."""
    if task_id not in tasks:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return tasks[task_id]


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "sentinel", "version": "1.0.0"}


async def _run_review_task(task_id: str, target_path: str, include_red_team: bool):
    """Background task: run the full Sentinel pipeline."""
    tasks[task_id]["status"] = "running"

    try:
        attestation = run_sentinel(target_path, verbose=False,
                                   include_red_team=include_red_team)

        red_team_result = None
        if include_red_team:
            red_team_result = run_red_team(target_path)

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
        tasks[task_id]["result"] = {
            "verdict": attestation.verdict,
            "findings_count": len(attestation.findings),
            "findings": [
                {
                    "title": f.title,
                    "severity": f.severity,
                    "pillar": f.pillar,
                    "evidence_ids": f.evidence_ids,
                    "remediation": f.remediation,
                }
                for f in attestation.findings
            ],
            "audit_ref": attestation.audit_ref,
            "signature": attestation.signature,
            "red_team": red_team_result,
        }
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["result"] = {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)