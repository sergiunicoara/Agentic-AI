import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.ingest.embedder import Embedder, get_openai_embedder
from app.retrieval.llm import LLMClient, get_anthropic_client
from app.retrieval.models import ChatEvent, ChatRequest
from app.retrieval.service import run_chat_turn

router = APIRouter()
logger = logging.getLogger(__name__)


def get_embedder() -> Embedder:
    return get_openai_embedder()


def get_llm_client() -> LLMClient:
    return get_anthropic_client()


async def _sse_stream(
    session: AsyncSession,
    embedder: Embedder,
    llm_client: LLMClient,
    request: ChatRequest,
) -> AsyncIterator[str]:
    try:
        async for event in run_chat_turn(
            session,
            embedder,
            llm_client,
            request.repo_id,
            request.conversation_id,
            request.message,
        ):
            yield f"data: {event.model_dump_json()}\n\n"
    except Exception:
        # Keep provider details out of logs as well as out of the SSE response.
        logger.error("chat_stream_failed", extra={"repo_id": str(request.repo_id)})
        await session.rollback()
        error_event = ChatEvent(type="error", text="Unable to complete the request.")
        yield f"data: {error_event.model_dump_json()}\n\n"


@router.post("/chat")
async def chat(
    request: ChatRequest,
    session: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
    llm_client: LLMClient = Depends(get_llm_client),
) -> StreamingResponse:
    return StreamingResponse(
        _sse_stream(session, embedder, llm_client, request),
        media_type="text/event-stream",
    )
