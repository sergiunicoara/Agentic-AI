import asyncio
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.db import session_factory
from app.ingest import chunker, store, walker
from app.ingest.embedder import FakeEmbedder, context_header
from app.retrieval.llm import FakeLLMClient
from app.retrieval.service import _load_history, run_chat_turn
from app.tables import messages as messages_table
from app.tables import repos as repos_table

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
TEST_SOURCE_URL = "test://chat-service"


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


async def _run_turn(repo_id, embedder, llm_client, conversation_id, question):
    async with session_factory()() as session:
        return [
            event
            async for event in run_chat_turn(
                session, embedder, llm_client, repo_id, conversation_id, question
            )
        ]


async def test_chat_turn_persists_message_with_parsed_citations():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)
    llm_client = FakeLLMClient()

    events = await _run_turn(repo_id, embedder, llm_client, None, "What does create_user do?")

    done = events[-1]
    assert done.type == "done"
    assert done.citations, "expected the fake LLM's canned citation to be parsed"
    assert done.final_text == "".join(event.text or "" for event in events if event.type == "delta")
    assert done.conversation_id is not None

    async with session_factory()() as session:
        rows = (
            await session.execute(
                select(messages_table).where(
                    messages_table.c.conversation_id == done.conversation_id
                )
            )
        ).all()

    assert len(rows) == 2
    roles = {row.role for row in rows}
    assert roles == {"user", "assistant"}
    assistant_row = next(row for row in rows if row.role == "assistant")
    assert assistant_row.citations


async def test_uncited_non_refusal_is_replaced_with_safe_response():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)
    events = await _run_turn(
        repo_id,
        embedder,
        FakeLLMClient(canned_answer="The database is PostgreSQL."),
        None,
        "What database is used?",
    )

    deltas = "".join(event.text or "" for event in events if event.type == "delta")
    assert deltas.strip() == "The database is PostgreSQL."
    assert events[-1].final_text == "I couldn't verify a cited answer from the retrieved context."
    assert events[-1].citations == []


async def test_first_delta_is_yielded_before_llm_completes():
    class ControlledLLM(FakeLLMClient):
        def __init__(self) -> None:
            super().__init__()
            self.first_delta = asyncio.Event()
            self.release = asyncio.Event()

        async def stream_reply(self, system, history, context, question):
            yield "partial answer "
            self.first_delta.set()
            await self.release.wait()
            yield "that is not cited"

    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)
    llm_client = ControlledLLM()
    events = []

    async def collect_events() -> None:
        async with session_factory()() as session:
            async for event in run_chat_turn(
                session, embedder, llm_client, repo_id, None, "A streaming question"
            ):
                events.append(event)

    task = asyncio.create_task(collect_events())
    await llm_client.first_delta.wait()
    assert not task.done()
    assert events[0].type == "delta"
    assert events[0].text == "partial answer "
    llm_client.release.set()
    await task
    assert events[-1].final_text == "I couldn't verify a cited answer from the retrieved context."


async def test_legitimate_refusal_without_citations_is_preserved():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)
    refusal = "I cannot verify that from the provided context."
    events = await _run_turn(
        repo_id, embedder, FakeLLMClient(canned_answer=refusal), None, "Unknown question"
    )

    assert events[-1].final_text.strip() == refusal
    assert events[-1].citations == []


async def test_invalid_citation_is_never_validated():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)
    events = await _run_turn(
        repo_id,
        embedder,
        FakeLLMClient(canned_answer="A factual answer [pkg/models.py:1-9999]."),
        None,
        "Question with a hallucinated range",
    )

    assert events[-1].citations == []
    assert events[-1].final_text == "I couldn't verify a cited answer from the retrieved context."


async def test_second_turn_includes_first_turn_in_history():
    embedder = FakeEmbedder()
    repo_id = await _ingest_fixture(embedder)
    llm_client = FakeLLMClient()

    first_events = await _run_turn(repo_id, embedder, llm_client, None, "First question?")
    conversation_id = first_events[-1].conversation_id

    await _run_turn(repo_id, embedder, llm_client, conversation_id, "Follow-up question?")

    assert llm_client.last_call is not None
    history = llm_client.last_call["history"]
    assert any(turn.role == "user" and "First question" in turn.content for turn in history)
    assert any(turn.role == "assistant" for turn in history)


async def test_history_is_scoped_to_repository() -> None:
    embedder = FakeEmbedder()
    repo_a = await _ingest_fixture(embedder)
    conversation_id = (await _run_turn(repo_a, embedder, FakeLLMClient(), None, "Repo A question"))[
        -1
    ].conversation_id
    assert conversation_id is not None

    async with session_factory()() as session:
        repo_b = await store.get_or_create_repo(session, "test://chat-service-repo-b")
        history = await _load_history(session, repo_b, conversation_id)
        await session.execute(
            delete(repos_table).where(repos_table.c.source_url == "test://chat-service-repo-b")
        )
        await session.commit()

    assert history == []
