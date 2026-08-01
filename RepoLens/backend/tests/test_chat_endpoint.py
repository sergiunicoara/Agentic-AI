from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.chat import get_embedder, get_llm_client
from app.db import session_factory
from app.ingest import chunker, store, walker
from app.ingest.embedder import FakeEmbedder, context_header
from app.main import app
from app.retrieval.llm import FakeLLMClient
from app.tables import messages as messages_table
from app.tables import repos as repos_table

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
TEST_SOURCE_URL = "test://chat-endpoint"


@pytest.fixture(autouse=True)
async def _clean_db():
    # repos.id -> files.repo_id -> chunks.file_id all cascade on delete, so scoping
    # this to our own source_url is enough — never blanket-delete files/chunks,
    # that would wipe every other repo's ingested data too. Messages are repository
    # scoped, but clearing test conversation rows keeps test setup isolated by ID.
    async with session_factory()() as session:
        await session.execute(delete(messages_table))
        await session.execute(
            delete(repos_table).where(repos_table.c.source_url == TEST_SOURCE_URL)
        )
        await session.commit()
    yield


async def _ingest_fixture(embedder):
    source_files = walker.walk(FIXTURE)
    async with session_factory()() as session:
        repo_id = await store.get_or_create_repo(session, TEST_SOURCE_URL)
        for source_file in source_files:
            text = source_file.abs_path.read_bytes().decode("utf-8")
            content_hash = store.compute_content_hash(text)
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


async def test_chat_endpoint_streams_sse_events():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)
    llm_client = FakeLLMClient(canned_answer="The answer is here without a validated citation.")

    app.dependency_overrides[get_embedder] = lambda: embedder
    app.dependency_overrides[get_llm_client] = lambda: llm_client
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat",
                json={"repo_id": str(repo_id), "message": "What does create_user do?"},
            )
        assert resp.status_code == 200
        body = resp.text
        assert '"type":"delta"' in body
        assert '"type":"done"' in body
        assert "I couldn't verify a cited answer from the retrieved context." in body
    finally:
        app.dependency_overrides.clear()


async def test_chat_endpoint_hides_internal_errors_in_sse():
    class ExplodingLLM(FakeLLMClient):
        async def stream_reply(self, system, history, context, question):
            raise RuntimeError("private provider detail")
            yield "never"

    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)
    app.dependency_overrides[get_embedder] = lambda: embedder
    app.dependency_overrides[get_llm_client] = ExplodingLLM
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat",
                json={"repo_id": str(repo_id), "message": "Trigger an error"},
            )
        assert resp.status_code == 200
        assert '"type":"error"' in resp.text
        assert "Unable to complete the request." in resp.text
        assert "private provider detail" not in resp.text
    finally:
        app.dependency_overrides.clear()
