"""FastMCP entrypoint. Run with: python -m app.mcp_server."""

import uuid

from fastmcp import FastMCP
from pydantic import BaseModel

from app.browse.models import FileContent, TreeNode
from app.browse.repo_map import build_repo_map, get_file_content
from app.db import session_factory
from app.ingest.embedder import get_openai_embedder
from app.observability import span
from app.retrieval.models import RetrievedChunk
from app.retrieval.search import search_chunks

mcp = FastMCP("Codex Code Documentation Assistant")


class SearchResult(BaseModel):
    file_path: str
    symbol_path: str
    kind: str
    start_line: int
    end_line: int
    content: str
    distance: float


@mcp.tool
async def search_code(repo_id: str, query: str, top_k: int = 8) -> list[SearchResult]:
    """Search indexed source code and return cited chunks."""
    with span("mcp.search_code", repo_id=repo_id, query=query, top_k=top_k):
        async with session_factory()() as session:
            chunks = await search_chunks(
                session, get_openai_embedder(), uuid.UUID(repo_id), query, top_k=top_k
            )
        return [_search_result(chunk) for chunk in chunks]


@mcp.tool
async def get_file(repo_id: str, path: str) -> FileContent:
    """Read an indexed source file by repository id and path."""
    with span("mcp.get_file", repo_id=repo_id, path=path):
        async with session_factory()() as session:
            result = await get_file_content(session, uuid.UUID(repo_id), path)
        if result is None:
            raise ValueError(f"No file at path {path!r} for this repo")
        return result


@mcp.tool
async def get_repo_map(repo_id: str) -> list[TreeNode]:
    """Return the clickable-style directory and symbol tree for a repository."""
    with span("mcp.get_repo_map", repo_id=repo_id):
        async with session_factory()() as session:
            return await build_repo_map(session, uuid.UUID(repo_id))


def _search_result(chunk: RetrievedChunk) -> SearchResult:
    return SearchResult(
        file_path=chunk.file_path,
        symbol_path=chunk.symbol_path,
        kind=chunk.kind,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        content=chunk.content,
        distance=chunk.distance,
    )


if __name__ == "__main__":
    mcp.run()
