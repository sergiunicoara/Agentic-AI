from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TranscriptIn(BaseModel):
    workspace_id: str = Field(min_length=2)
    source: str = "upload"
    external_id: str | None = None
    title: str = Field(min_length=3)
    text: str = Field(min_length=40)


class AskIn(BaseModel):
    workspace_id: str
    query: str = Field(min_length=5)
    top_k: int = Field(default=10, ge=1, le=50)


class Citation(BaseModel):
    document_id: str
    chunk_id: str
    snippet: str


class AskOut(BaseModel):
    answer: str
    citations: list[Citation]
    unknown: bool


class RetrievedChunk(BaseModel):
    """Transport type used throughout retrieval, evaluation, and tracing."""

    id: str = Field(..., description="Chunk UUID")
    document_id: str
    chunk_index: int | None = None
    text: str
    score: float = 0.0
    meta: dict[str, Any] = Field(default_factory=dict)


class GenOut(BaseModel):
    answer: str
    unknown: bool
    citations: list[Citation]
    followups: list[str] = []
