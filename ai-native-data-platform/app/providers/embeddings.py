from __future__ import annotations
import hashlib
import os
import numpy as np
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

EMBED_DIM = settings.embed_dim
PROVIDER = os.getenv("EMBED_PROVIDER", "mock").lower()
TIMEOUT = float(os.getenv("REQUEST_TIMEOUT_S", "20"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

def _hash_to_vec(s: str, dim: int) -> np.ndarray:
    # Python's built-in hash is randomized per process. A SHA-256-derived seed
    # keeps mock embeddings identical across API/worker processes and restarts.
    seed = int.from_bytes(hashlib.sha256(s.encode("utf-8", errors="ignore")).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    v = rng.normal(size=dim).astype(np.float32)
    v /= (np.linalg.norm(v) + 1e-12)
    return v

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.3, min=0.3, max=3))
def _openai_embed(text: str) -> list[float]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing but EMBED_PROVIDER=openai")

    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {"model": OPENAI_EMBED_MODEL, "input": text}
    if OPENAI_EMBED_MODEL.startswith("text-embedding-3"):
        payload["dimensions"] = EMBED_DIM

    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

    vec = data["data"][0]["embedding"]
    if not isinstance(vec, list):
        raise RuntimeError("Unexpected embeddings response shape")
    _validate_dimensions(vec)
    return vec

def embed(text: str) -> list[float]:
    text = (text or "").strip()
    if len(text) < 3:
        text = "empty"

    if PROVIDER == "openai":
        return _openai_embed(text)

    return _hash_to_vec(text, EMBED_DIM).tolist()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.3, min=0.3, max=3))
def _openai_embed_batch(texts: list[str]) -> list[list[float]]:
    """Batch embeddings via the OpenAI embeddings endpoint.

    Notes:
    - OpenAI accepts a list in `input`.
    - The response order matches the input order.

    This is used by the large-corpus indexing pipeline to amortize request
    overhead and improve throughput.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing but EMBED_PROVIDER=openai")

    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {"model": OPENAI_EMBED_MODEL, "input": texts}
    if OPENAI_EMBED_MODEL.startswith("text-embedding-3"):
        payload["dimensions"] = EMBED_DIM

    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

    rows = data.get("data") or []
    # API returns list of objects with an `embedding` field.
    out: list[list[float]] = []
    for row in rows:
        vec = row.get("embedding")
        if not isinstance(vec, list):
            raise RuntimeError("Unexpected embeddings batch response shape")
        _validate_dimensions(vec)
        out.append(vec)
    if len(out) != len(texts):
        raise RuntimeError("Embeddings batch size mismatch")
    return out


def _validate_dimensions(vec: list[float]) -> None:
    if len(vec) != EMBED_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch: provider returned {len(vec)}, expected {EMBED_DIM}. "
            "Set EMBED_DIM to match the pgvector column and request that dimension from the provider."
        )


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed many inputs.

    For the mock provider we deterministically hash each string.
    """
    cleaned: list[str] = []
    for t in texts:
        s = (t or "").strip()
        if len(s) < 3:
            s = "empty"
        cleaned.append(s)

    if PROVIDER == "openai":
        return _openai_embed_batch(cleaned)

    return [_hash_to_vec(s, EMBED_DIM).tolist() for s in cleaned]
