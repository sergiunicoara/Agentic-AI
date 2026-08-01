import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.embedder import Embedder
from app.observability import span
from app.retrieval.citations import extract_citations, validate_citations
from app.retrieval.context import assemble_context
from app.retrieval.llm import SYSTEM_PROMPT, LLMClient
from app.retrieval.models import ChatEvent, ChatTurn, Citation
from app.retrieval.search import search_chunks
from app.tables import messages as messages_table

HISTORY_LIMIT = 10
logger = logging.getLogger(__name__)
_REFUSAL_RE = re.compile(
    r"\b(?:cannot|can't|do not|don't|unable to|not enough|no information|not found)\b",
    re.IGNORECASE,
)
SAFE_UNCITED_RESPONSE = "I couldn't verify a cited answer from the retrieved context."


async def _load_history(
    session: AsyncSession, repo_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[ChatTurn]:
    stmt = (
        select(messages_table.c.role, messages_table.c.content)
        .where(
            messages_table.c.repo_id == repo_id,
            messages_table.c.conversation_id == conversation_id,
        )
        .order_by(messages_table.c.created_at.desc())
        .limit(HISTORY_LIMIT)
    )
    result = await session.execute(stmt)
    rows = list(result)[::-1]
    return [ChatTurn(role=row.role, content=row.content) for row in rows]


async def _persist_message(
    session: AsyncSession,
    repo_id: uuid.UUID,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    citations: list[Citation] | None = None,
) -> None:
    await session.execute(
        messages_table.insert().values(
            id=uuid.uuid4(),
            repo_id=repo_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            citations=[c.model_dump() for c in citations] if citations else None,
            created_at=datetime.now(UTC),
        )
    )


async def run_chat_turn(
    session: AsyncSession,
    embedder: Embedder,
    llm_client: LLMClient,
    repo_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    question: str,
) -> AsyncIterator[ChatEvent]:
    """Retrieve → assemble context → stream the LLM reply → parse citations → persist
    both turns. Yields `delta` events as the answer streams, then one `done` event
    carrying the parsed citations and the (possibly newly created) conversation_id."""
    conv_id = conversation_id or uuid.uuid4()
    history = await _load_history(session, repo_id, conv_id) if conversation_id else []

    with span("chat.query", repo_id=repo_id, question=question):
        retrieved = await search_chunks(session, embedder, repo_id, question)
        context, used_chunks = assemble_context(retrieved)

    await _persist_message(session, repo_id, conv_id, "user", question)
    # Release the database transaction before waiting on the external model stream.
    await session.commit()

    answer_parts: list[str] = []
    with span("chat.llm", model=type(llm_client).__name__):
        async for delta in llm_client.stream_reply(SYSTEM_PROMPT, history, context, question):
            answer_parts.append(delta)
            # Provisional deltas are intentionally visible immediately. The frontend
            # replaces this content with done.final_text once citation validation completes.
            yield ChatEvent(type="delta", text=delta)

    full_answer = "".join(answer_parts)
    extracted_citations = extract_citations(full_answer)
    citations = validate_citations(extracted_citations, used_chunks)
    invalid_count = len(extracted_citations) - len(citations)
    if invalid_count:
        logger.warning("discarded_invalid_citations", extra={"count": invalid_count})
    if extracted_citations and not citations:
        logger.warning("no_valid_citations_in_answer")
    accepted_answer = full_answer
    if not citations and full_answer.strip() and not _REFUSAL_RE.search(full_answer):
        logger.warning("uncited_non_refusal_answer_replaced")
        accepted_answer = SAFE_UNCITED_RESPONSE

    await _persist_message(session, repo_id, conv_id, "assistant", accepted_answer, citations)
    await session.commit()

    yield ChatEvent(
        type="done",
        final_text=accepted_answer,
        citations=citations,
        conversation_id=conv_id,
    )
