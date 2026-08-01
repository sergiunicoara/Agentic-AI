from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class RepoSummary(BaseModel):
    id: UUID
    source_url: str
    file_count: int
    chunk_count: int
    indexed_at: str | None = None


class SymbolNode(BaseModel):
    symbol_path: str
    kind: str
    start_line: int
    end_line: int
    children: list["SymbolNode"] = []


class TreeNode(BaseModel):
    type: Literal["dir", "file"]
    name: str
    path: str | None = None
    symbols: list[SymbolNode] = []
    children: list["TreeNode"] = []


class FileContent(BaseModel):
    path: str
    content: str
    language: str | None = None
