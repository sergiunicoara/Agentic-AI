from __future__ import annotations

"""Groundedness utilities.

These are intentionally lightweight (string containment) so they can be:
  - enforced online (cheap)
  - reused in offline evaluation

The rest of the system models retrieved context chunks as the Pydantic
`RetrievedChunk` schema, which serializes as `{id, text, ...}`. Earlier
iterations of this scaffold used `{chunk_id, chunk_text}`.

To avoid brittle call sites, we accept either shape here.
"""

def verify_citation_snippets(contexts: list[dict], citations: list[dict]) -> tuple[bool, str]:
    # Support both historical shapes:
    #   - contexts from RetrievedChunk.model_dump(): {"id": ..., "text": ...}
    #   - contexts from older pipelines: {"chunk_id": ..., "chunk_text": ...}
    ctx_by_id: dict[str, str] = {}
    for c in contexts:
        cid = (c.get("chunk_id") or c.get("id") or "").strip()
        txt = c.get("chunk_text") or c.get("text") or ""
        if cid:
            ctx_by_id[cid] = str(txt)
    for c in citations:
        cid = c.get("chunk_id")
        snippet = (c.get("snippet") or "").strip()
        if not cid or cid not in ctx_by_id:
            return False, "citation_chunk_id_not_in_contexts"
        if not snippet:
            return False, "empty_snippet"
        if snippet not in ctx_by_id[cid]:
            return False, "snippet_not_substring_of_chunk"
    return True, "ok"

def evidence_minimum(citations: list[dict], min_chars: int = 80) -> tuple[bool, str]:
    total = sum(len((c.get("snippet") or "")) for c in citations)
    if total < min_chars:
        return False, "insufficient_evidence"
    return True, "ok"
