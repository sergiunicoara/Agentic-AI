from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.repos import router as repos_router
from app.config import get_settings
from app.db import check_connection
from app.ingest.embedder import close_openai_embedder
from app.retrieval.llm import close_anthropic_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_openai_embedder()
    await close_anthropic_client()

app = FastAPI(title="Codex — Code Documentation Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(repos_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    await check_connection()
    return {"status": "ok"}
