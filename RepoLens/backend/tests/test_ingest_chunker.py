from pathlib import Path

from app.ingest import chunker, walker
from app.ingest.chunker import TOKEN_CEILING
from app.ingest.models import ChunkKind, ChunkRecord, SourceFile
from app.tokens import count_tokens

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _all_fixture_chunks() -> tuple[list[SourceFile], list[ChunkRecord]]:
    files = walker.walk(FIXTURE)
    chunks: list[ChunkRecord] = []
    for f in files:
        chunks.extend(chunker.chunk_file(f))
    return files, chunks


def test_line_range_fidelity() -> None:
    """Mandatory per spec: reading the source file at [start_line, end_line] must
    reproduce every chunk's content verbatim. A wrong citation is worse than none."""
    files, chunks = _all_fixture_chunks()
    by_path = {f.path: f for f in files}

    assert chunks, "fixture repo produced no chunks at all"

    for chunk in chunks:
        source_file = by_path[chunk.file_path]
        raw = source_file.abs_path.read_bytes().decode("utf-8")
        source_lines = raw.splitlines(keepends=True)
        expected = "".join(source_lines[chunk.start_line - 1 : chunk.end_line])
        location = f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
        assert chunk.content == expected, f"drift in {location}"


def test_module_preamble_captured() -> None:
    _, chunks = _all_fixture_chunks()
    module_chunk = next(
        c for c in chunks if c.file_path == "pkg/models.py" and c.kind == ChunkKind.MODULE
    )
    assert module_chunk.start_line == 1
    assert "DEFAULT_TIMEOUT" in module_chunk.content


def test_token_ceiling_split_preserves_contiguous_ranges() -> None:
    _, chunks = _all_fixture_chunks()
    pipeline_chunks = [
        c
        for c in chunks
        if c.file_path == "pkg/utils.py" and c.symbol_path == "pkg.utils.long_running_pipeline"
    ]

    assert len(pipeline_chunks) > 1, "expected the long function to be split across multiple chunks"
    for c in pipeline_chunks:
        assert count_tokens(c.content) <= TOKEN_CEILING

    sorted_chunks = sorted(pipeline_chunks, key=lambda c: c.start_line)
    for a, b in zip(sorted_chunks, sorted_chunks[1:]):
        assert b.start_line == a.end_line + 1


def test_markdown_heading_breadcrumbs() -> None:
    _, chunks = _all_fixture_chunks()
    breadcrumbs = {c.symbol_path for c in chunks if c.file_path == "README.md"}

    assert "Sample Repo" in breadcrumbs
    assert "Sample Repo > Setup > Installation" in breadcrumbs
    assert "Sample Repo > Setup > Configuration" in breadcrumbs
    assert "Sample Repo > Usage" in breadcrumbs


def test_decorated_route_is_chunked_once_with_exact_range() -> None:
    _, chunks = _all_fixture_chunks()
    route_chunks = [
        chunk
        for chunk in chunks
        if chunk.file_path == "pkg/routes.py" and chunk.symbol_path == "pkg.routes.list_users"
    ]

    assert len(route_chunks) == 1
    assert route_chunks[0].start_line == 4
    assert route_chunks[0].end_line == 6
    assert '@router.get("/users")' in route_chunks[0].content
