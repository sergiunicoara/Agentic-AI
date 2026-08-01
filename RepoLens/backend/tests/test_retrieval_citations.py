from uuid import uuid4

from app.retrieval.citations import extract_citations, validate_citations
from app.retrieval.models import Citation, RetrievedChunk


def test_extract_single_citation():
    answer = "The router is defined here [fastapi/routing.py:120-148]."
    assert extract_citations(answer) == [
        Citation(file="fastapi/routing.py", start_line=120, end_line=148)
    ]


def test_extract_multiple_citations_in_order():
    answer = "See [a/b.py:1-5] and also [c/d.py:10-20] for details."
    assert extract_citations(answer) == [
        Citation(file="a/b.py", start_line=1, end_line=5),
        Citation(file="c/d.py", start_line=10, end_line=20),
    ]


def test_no_citations_returns_empty_list():
    assert extract_citations("I don't know based on the given context.") == []


def test_ignores_bracketed_text_without_line_range():
    answer = "This uses [markdown-style links](http://example.com) but cites nothing."
    assert extract_citations(answer) == []


def test_citations_are_limited_to_exact_context_ranges():
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        file_path="pkg/models.py",
        symbol_path="create_user",
        kind="function",
        start_line=18,
        end_line=20,
        content="pass",
        token_count=1,
        distance=0.1,
    )
    citations = extract_citations("Good [pkg/models.py:18-20] bad [pkg/models.py:1-9999]")
    assert validate_citations(citations, [chunk]) == [citations[0]]
