# app/models.py
from typing import List, Optional

from pydantic import BaseModel, Field


class Job(BaseModel):
    text: str = Field(..., description="Raw job description text pasted by the user.")


class MatchRequest(BaseModel):
    job: Job


class Summary(BaseModel):
    overall_fit: str
    strengths: List[str]
    risks: List[str]
    recommended_talking_points: List[str]


class Insight(BaseModel):
    requirement: str
    evidence: str
    confidence: float
    comment: str


class MatchResponse(BaseModel):
    job: Job
    summary: Summary
    insights: List[Insight]
    judge_passed: bool
    judge_reason: str
