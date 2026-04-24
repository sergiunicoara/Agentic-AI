from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TranscriptIn(BaseModel):
    workspace_id: str = Field(min_length=2, max_length=128)
    source: str = Field(default="upload", max_length=256)
    external_id: str | None = Field(default=None, max_length=512)
    title: str = Field(min_length=3, max_length=500)
    text: str = Field(min_length=40, max_length=500_000)


class AskIn(BaseModel):
    workspace_id: str = Field(min_length=2, max_length=128)
    query: str = Field(min_length=5, max_length=2_000)
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
    modality: str = "text"      # text | image
    caption: str | None = None  # populated for image chunks; used as retrieval text
    meta: dict[str, Any] = Field(default_factory=dict)


class GenOut(BaseModel):
    answer: str
    unknown: bool
    citations: list[Citation]
    followups: list[str] = []


class NLQueryIn(BaseModel):
    workspace_id: str = Field(min_length=2, max_length=128)
    query: str = Field(min_length=5, max_length=500)


class NLQueryOut(BaseModel):
    sql: str
    results: list[dict[str, Any]]
    row_count: int


class ImageIngestOut(BaseModel):
    status: str
    page_count: int
