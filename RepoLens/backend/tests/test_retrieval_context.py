import uuid

from app.retrieval.context import TOKEN_BUDGET, assemble_context, render_chunk
from app.retrieval.models import RetrievedChunk
from app.tokens import count_tokens


def _make_chunk(content: str, path: str = "a.py") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        file_path=path,
        symbol_path="a.foo",
        kind="function",
        start_line=1,
        end_line=1 + content.count("\n"),
        content=content,
        token_count=count_tokens(content),
        distance=0.0,
    )


def test_assemble_context_respects_budget_and_preserves_order():
    chunk_content = "x = 1\n" * 700  # ~1,400 tokens per chunk
    chunks = [_make_chunk(chunk_content, path=f"f{i}.py") for i in range(8)]

    context, included = assemble_context(chunks)

    assert 1 <= len(included) < len(chunks), "budget should stop inclusion before all chunks fit"
    assert [c.file_path for c in included] == [c.file_path for c in chunks[: len(included)]]

    total_tokens = sum(count_tokens(render_chunk(c)) for c in included)
    assert total_tokens <= TOKEN_BUDGET

    for c in included:
        assert c.content in context


def test_assemble_context_always_includes_at_least_one_chunk_even_if_oversized():
    huge_content = "x = 1\n" * 20000  # comfortably over TOKEN_BUDGET on its own
    chunks = [_make_chunk(huge_content)]

    context, included = assemble_context(chunks)

    assert len(included) == 1
    assert included[0].content in context


def test_assemble_context_empty_input():
    context, included = assemble_context([])
    assert context == ""
    assert included == []
