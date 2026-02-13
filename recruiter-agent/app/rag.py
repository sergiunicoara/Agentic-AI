from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseModel


class RAGChunk(BaseModel):
    id: str
    source: str
    text: str


def _load_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


def load_corpus(cv_path: str, portfolio_path: str) -> List[RAGChunk]:
    chunks: List[RAGChunk] = []

    cv = _load_text(cv_path)
    if cv:
        chunks.append(RAGChunk(id="cv", source="cv", text=cv))

    portfolio = _load_text(portfolio_path)
    if portfolio:
        chunks.append(RAGChunk(id="portfolio", source="portfolio", text=portfolio))

    return chunks


def naive_search(query: str, chunks: List[RAGChunk]) -> List[RAGChunk]:
    q = query.lower()
    scored: list[tuple[int, RAGChunk]] = []
    for ch in chunks:
        score = ch.text.lower().count(q) if q else 0
        scored.append((score, ch))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in scored if s > 0][:5]
