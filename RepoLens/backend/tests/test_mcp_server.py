from uuid import UUID

from app.mcp_server import _search_result
from app.retrieval.models import RetrievedChunk


def test_mcp_search_result_preserves_citation_range():
    result = _search_result(
        RetrievedChunk(
            chunk_id=UUID("00000000-0000-0000-0000-000000000001"),
            file_path="pkg/models.py",
            symbol_path="pkg.models.create_user",
            kind="function",
            start_line=18,
            end_line=20,
            content="def create_user():\n    return User()",
            token_count=8,
            distance=0.12,
        )
    )

    assert result.file_path == "pkg/models.py"
    assert result.start_line == 18
    assert result.end_line == 20
