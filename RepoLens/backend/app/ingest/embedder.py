import hashlib
from functools import lru_cache
from typing import Protocol

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

_BATCH_SIZE = 100


class Embedder(Protocol):
    dim: int

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


def context_header(
    repo: str, path: str, symbol_path: str, docstring_first_line: str, code: str
) -> str:
    """Prepended to each chunk before embedding — never stored in the `content` column."""
    header = f"# {repo}/{path} :: {symbol_path}"
    if docstring_first_line:
        header += f"\n{docstring_first_line}"
    return f"{header}\n\n{code}"


class OpenAIEmbedder:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.embedding_model
        self.dim = settings.embedding_dim

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=20))
    async def _embed_one_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            results.extend(await self._embed_one_batch(texts[i : i + _BATCH_SIZE]))
        return results

    async def aclose(self) -> None:
        await self._client.close()


class FakeEmbedder:
    """Deterministic, offline embedder — used in tests and `--fake-embeddings` dry runs
    so the pipeline is fully testable without a real OpenAI key or network access."""

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 for i in range(self.dim)]


@lru_cache
def get_openai_embedder() -> OpenAIEmbedder:
    return OpenAIEmbedder()


async def close_openai_embedder() -> None:
    if get_openai_embedder.cache_info().currsize:
        await get_openai_embedder().aclose()
        get_openai_embedder.cache_clear()
