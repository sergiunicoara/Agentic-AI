from pathlib import Path

import pytest
from sqlalchemy import delete

from app.db import session_factory
from app.ingest import chunker, store, walker
from app.ingest.embedder import FakeEmbedder, context_header
from app.retrieval.search import search_chunks_hybrid
from app.tables import repos as repos_table

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
SOURCE_URL = "test://retrieval-hybrid"


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


async def test_hybrid_search_surfaces_bm25_keyword_match() -> None:
    """create_user is a distinctive lexical token BM25 ranks highly even though
    FakeEmbedder's vector distance is meaningless noise for a natural-language
    query — proves RRF fusion actually pulls in the BM25-ranked result."""
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)

    async with session_factory()() as session:
        results = await search_chunks_hybrid(
            session, embedder, repo_id, "create_user factory function", top_k=5
        )

    assert any(r.symbol_path == "pkg.models.create_user" for r in results)


async def test_hybrid_search_scoped_to_repo_id_and_capped_at_top_k() -> None:
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)

    async with session_factory()() as session:
        results = await search_chunks_hybrid(session, embedder, repo_id, "user", top_k=3)

    assert len(results) <= 3
    assert all(r.file_path for r in results)
