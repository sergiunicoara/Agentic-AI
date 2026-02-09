from __future__ import annotations

def contains_all(text: str, phrases: list[str]) -> bool:
    t = (text or "").lower()
    return all(p.lower() in t for p in phrases)

def contains_any(text: str, phrases: list[str]) -> bool:
    t = (text or "").lower()
    return any(p.lower() in t for p in phrases)

def citation_present(citations: list[dict]) -> float:
    return 1.0 if citations else 0.0

def unknown_correctness(pred_unknown: bool, expect_unknown: bool) -> float:
    return 1.0 if pred_unknown == expect_unknown else 0.0


def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """Binary recall@k over ids (doc ids or chunk ids).

    Returns 1.0 if any relevant id appears in the top-k retrieved list, else 0.0.
    """
    if not relevant_ids:
        return 0.0
    top = set((retrieved_ids or [])[: max(1, k)])
    return 1.0 if any(rid in top for rid in relevant_ids) else 0.0


def mrr(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
    """Mean reciprocal rank for a single query."""
    if not relevant_ids:
        return 0.0
    rel = set(relevant_ids)
    for i, rid in enumerate(retrieved_ids or [], start=1):
        if rid in rel:
            return 1.0 / i
    return 0.0
