from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_factory
from app.ingest import chunker, store, walker
from app.ingest.embedder import Embedder, FakeEmbedder, context_header
from app.ingest.models import SourceFile
from app.tables import chunks as chunks_table
from app.tables import files as files_table
from app.tables import repos as repos_table

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
TEST_SOURCE_URL = "test://sample-repo"


@pytest.fixture(autouse=True)
async def _clean_db():
    # repos.id -> files.repo_id -> chunks.file_id all cascade on delete, so scoping
    # this to our own source_url is enough — never blanket-delete files/chunks,
    # that would wipe every other repo's ingested data too.
    async with session_factory()() as session:
        await session.execute(
            delete(repos_table).where(repos_table.c.source_url == TEST_SOURCE_URL)
        )
        await session.commit()
    yield


async def _ingest_all(
    session: AsyncSession, source_files: list[SourceFile], repo_id, embedder: Embedder
) -> int:
    total = 0
    for source_file in source_files:
        text = source_file.abs_path.read_bytes().decode("utf-8")
        content_hash = store.compute_content_hash(text)
        existing = await store.existing_file_hash(session, repo_id, source_file.path)
        if existing == content_hash:
            continue
        records = chunker.chunk_file(source_file)
        embeddings = []
        if records:
            inputs = [
                context_header(
                    TEST_SOURCE_URL,
                    source_file.path,
                    c.symbol_path,
                    c.docstring_first_line,
                    c.content,
                )
                for c in records
            ]
            embeddings = await embedder.embed_batch(inputs)
        total += await store.replace_file(
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
    return total


async def test_ingest_pipeline_populates_tables() -> None:
    source_files = walker.walk(FIXTURE)
    embedder = FakeEmbedder()

    async with session_factory()() as session:
        repo_id = await store.get_or_create_repo(session, TEST_SOURCE_URL)
        total_chunks = await _ingest_all(session, source_files, repo_id, embedder)
        await store.finalize_repo_counts(session, repo_id)
        await session.commit()

    assert total_chunks > 0

    async with session_factory()() as session:
        file_rows = (
            await session.execute(select(files_table).where(files_table.c.repo_id == repo_id))
        ).all()
        chunk_rows = (
            await session.execute(
                select(chunks_table)
                .join(files_table, chunks_table.c.file_id == files_table.c.id)
                .where(files_table.c.repo_id == repo_id)
            )
        ).all()

    assert len(file_rows) == len(source_files)
    assert len(chunk_rows) == total_chunks


async def test_unchanged_file_is_skipped_on_second_run() -> None:
    source_files = walker.walk(FIXTURE)
    embedder = FakeEmbedder()

    async with session_factory()() as session:
        repo_id = await store.get_or_create_repo(session, TEST_SOURCE_URL)
        await _ingest_all(session, source_files, repo_id, embedder)
        await session.commit()

    async with session_factory()() as session:
        second_run_chunks = await _ingest_all(session, source_files, repo_id, embedder)
        await session.commit()

    assert second_run_chunks == 0, "unchanged files should be skipped, not re-embedded"


async def test_removed_source_file_is_deleted_on_snapshot_refresh() -> None:
    source_files = walker.walk(FIXTURE)
    embedder = FakeEmbedder()

    async with session_factory()() as session:
        repo_id = await store.get_or_create_repo(session, TEST_SOURCE_URL)
        await _ingest_all(session, source_files, repo_id, embedder)
        current_paths = {source_file.path for source_file in source_files}
        removed_path = next(iter(current_paths))
        assert (
            await store.delete_missing_files(session, repo_id, current_paths - {removed_path})
            == 1
        )
        await session.commit()

    async with session_factory()() as session:
        remaining = await session.execute(
            select(files_table.c.path).where(files_table.c.repo_id == repo_id)
        )
        assert removed_path not in {row.path for row in remaining}
