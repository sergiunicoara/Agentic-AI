from pathlib import Path

import pytest
from sqlalchemy import delete

from app.db import session_factory
from app.ingest import chunker, store, walker
from app.ingest.embedder import FakeEmbedder, context_header
from app.retrieval.search import search_chunks
from app.tables import repos as repos_table

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
SOURCE_A = "test://retrieval-search-a"
SOURCE_B = "test://retrieval-search-b"


@pytest.fixture(autouse=True)
async def _clean_db():
    # repos.id -> files.repo_id -> chunks.file_id all cascade on delete, so scoping
    # this to our own source_urls is enough — never blanket-delete files/chunks,
    # that would wipe every other repo's ingested data too.
    async with session_factory()() as session:
        await session.execute(
            delete(repos_table).where(repos_table.c.source_url.in_([SOURCE_A, SOURCE_B]))
        )
        await session.commit()
    yield


async def _ingest_fixture(embedder, source_url: str):
    source_files = walker.walk(FIXTURE)
    async with session_factory()() as session:
        repo_id = await store.get_or_create_repo(session, source_url)
        for source_file in source_files:
            text = source_file.abs_path.read_bytes().decode("utf-8")
            content_hash = store.compute_content_hash(text)
            records = chunker.chunk_file(source_file)
            embeddings = []
            if records:
                inputs = [
                    context_header(
                        source_url,
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


async def test_search_returns_exact_match_first():
    """FakeEmbedder is a deterministic hash of its input text, so querying with the
    exact same text that was embedded for a chunk must rank that chunk at distance
    ~0 — this proves the SQL ordering/top-k mechanics work, not semantic relevance
    (that requires the real embedding model and is a Phase 4 eval concern)."""
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder, SOURCE_A)

    source_files = walker.walk(FIXTURE)
    models_file = next(f for f in source_files if f.path == "pkg/models.py")
    records = chunker.chunk_file(models_file)
    target = next(r for r in records if r.symbol_path == "pkg.models.create_user")
    query = context_header(
        SOURCE_A, "pkg/models.py", target.symbol_path, target.docstring_first_line, target.content
    )

    async with session_factory()() as session:
        results = await search_chunks(session, embedder, repo_id, query, top_k=5)

    assert results
    assert results[0].symbol_path == "pkg.models.create_user"
    assert results[0].distance < 1e-6


async def test_search_scopes_results_to_repo_id():
    """Both repos ingest the identical fixture. A scoping bug in the JOIN/WHERE would
    silently return both repositories' rows, so assert the
    exact count for one repo rather than just "some results came back"."""
    embedder = FakeEmbedder()
    repo_id_a = await _ingest_fixture(embedder, SOURCE_A)
    await _ingest_fixture(embedder, SOURCE_B)

    async with session_factory()() as session:
        results = await search_chunks(session, embedder, repo_id_a, "create_user", top_k=100)

    assert len(results) == 23
