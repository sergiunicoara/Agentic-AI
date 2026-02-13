# app/routes.py
from fastapi import APIRouter
from app.models import MatchRequest, MatchResponse
from app.agent import analyze_match   # <-- use the real Gemini agent

router = APIRouter()

@router.post("/match", response_model=MatchResponse)
def match_endpoint(request: MatchRequest):
    """
    Recruiter matching endpoint using Gemini model.
    """
    return analyze_match(request)
