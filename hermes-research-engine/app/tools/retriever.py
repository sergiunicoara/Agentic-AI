"""RAG retrieval tool backed by LanceDB long-term memory."""
from __future__ import annotations

from typing import List

from app.memory.long_term import long_term_memory


def retrieve_knowledge(query: str, k: int = 5) -> List[dict]:
    """Semantic search over the persistent knowledge base."""
    return long_term_memory.search(query, k=k)


def ingest_document(doc_id: str, text: str, source: str = "") -> str:
    long_term_memory.ingest(doc_id, text, source)
    return f"Ingested document '{doc_id}' ({len(text)} chars)"
