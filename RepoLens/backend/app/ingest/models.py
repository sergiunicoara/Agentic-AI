from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel


class ChunkKind(StrEnum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    MARKDOWN_SECTION = "markdown_section"


class SourceFile(BaseModel):
    """A file selected by the walker, relative to the repo root."""

    path: str
    abs_path: Path
    language: str


class ParsedSymbol(BaseModel):
    """A top-level function/class/method extracted by the parser, before chunking."""

    symbol_path: str
    kind: ChunkKind
    start_line: int
    end_line: int
    code: str
    docstring_first_line: str = ""


class ChunkRecord(BaseModel):
    """A chunk ready to embed and upsert. Mirrors the `chunks` table columns."""

    file_path: str
    symbol_path: str
    kind: ChunkKind
    start_line: int
    end_line: int
    content: str
    token_count: int
    docstring_first_line: str = ""


class FileRecord(BaseModel):
    path: str
    language: str
    loc: int
    content_hash: str
    chunks: list[ChunkRecord]
