"""
FastAPI backend — ties everything together.
"""
from __future__ import annotations
import asyncio
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from agents.coordinator import CoordinatorAgent
from agents.session_manager import SessionManager
from api.human_review import HumanReviewQueue
from schemas.rca_output import RCAOutput, AgentError

logger = logging.getLogger(__name__)
app = FastAPI(title="Enterprise AI Incident Investigator", version="1.0.0")
session_mgr = SessionManager()
review_queue = HumanReviewQueue()


class InvestigateRequest(BaseModel):
    ticket_id: str
    ticket_content: str
    resume_session_id: str | None = None


@app.post("/investigate", response_model=dict)
async def investigate(req: InvestigateRequest, background_tasks: BackgroundTasks):
    """
    Main investigation endpoint.
    Resumes session if session_id provided (D1.7).
    """
    if req.resume_session_id:
        session = session_mgr.resume(req.resume_session_id)
    else:
        session = session_mgr.create(req.ticket_id)

    coordinator = CoordinatorAgent()
    result = await coordinator.investigate(req.ticket_content, req.ticket_id)

    if isinstance(result, AgentError):
        # D5.3: Structured error propagation — never raw HTTP 500
        raise HTTPException(status_code=422, detail=result.model_dump())

    # D5.2: Escalation handling
    if result.escalate:
        background_tasks.add_task(review_queue.enqueue, result)

    session_mgr.complete(session.session_id)
    return {
        "status": "ok",
        "session_id": session.session_id,
        "data": result.to_api_response(),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
