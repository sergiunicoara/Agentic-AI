from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    chunk_id: UUID
    file_path: str
    symbol_path: str
    kind: str
    start_line: int
    end_line: int
    content: str
    token_count: int
    distance: float


class Citation(BaseModel):
    file: str
    start_line: int
    end_line: int


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    repo_id: UUID
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=8_000)


class ChatEvent(BaseModel):
    type: Literal["delta", "done", "error"]
    text: str | None = None
    final_text: str | None = None
    citations: list[Citation] | None = None
    conversation_id: UUID | None = None
