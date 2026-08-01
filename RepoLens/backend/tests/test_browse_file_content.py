from pathlib import Path

import pytest
from sqlalchemy import delete

from app.browse.repo_map import get_file_content
from app.db import session_factory
from app.ingest import chunker, store, walker
from app.ingest.embedder import FakeEmbedder, context_header
from app.tables import repos as repos_table

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
SOURCE_URL = "test://browse-file-content"


@pytest.fixture(autouse=True)
async def _clean_db():
    # repos.id -> files.repo_id -> chunks.file_id all cascade on delete, so scoping
    # this to our own source_url is enough — never blanket-delete files/chunks,
    # that would wipe every other repo's ingested data too.
    async with session_factory()() as session:
        await session.execute(delete(repos_table).where(repos_table.c.source_url == SOURCE_URL))
        await session.commit()
    yield


async def _ingest_fixture(embedder):
    source_files = walker.walk(FIXTURE)
    async with session_factory()() as session:
        repo_id = await store.get_or_create_repo(session, SOURCE_URL)
        for source_file in source_files:
            text = source_file.abs_path.read_bytes().decode("utf-8")
            content_hash = store.compute_content_hash(text)
            records = chunker.chunk_file(source_file)
            embeddings = []
            if records:
                inputs = [
                    context_header(
                        SOURCE_URL,
                        source_file.path,
                        c.symbol_path,
                        c.docstring_first_line,
                        c.content,
                    )
                    for c in records
                ]
                embeddings = await embedder.embed_batch(inputs)
            await store.replace_file(
                session,
                repo_id,
                source_file.path,
                source_file.language,
                text.count("\n") + 1,
                content_hash,
                text,
                records,
                embeddings,
            )
        await store.finalize_repo_counts(session, repo_id)
        await session.commit()
    return repo_id


async def test_get_file_content_matches_source_exactly():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)

    expected = (FIXTURE / "pkg" / "models.py").read_bytes().decode("utf-8")

    async with session_factory()() as session:
        result = await get_file_content(session, repo_id, "pkg/models.py")

    assert result is not None
    assert result.content == expected
    assert result.language == "python"


async def test_get_file_content_returns_none_for_unknown_path():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)

    async with session_factory()() as session:
        result = await get_file_content(session, repo_id, "does/not/exist.py")

    assert result is None
