from __future__ import annotations

import json
import time
import uuid

from pydantic import ValidationError

from app.core.observability import GEN_FAILURES, GEN_LATENCY, persist_trace, timer
from app.schemas import GenOut, RetrievedChunk
from app.providers.llm import generate


class GenerationFailure(RuntimeError):
    """Classified generation failure used for reliability and observability."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def build_prompt(query: str, contexts: list[RetrievedChunk]) -> str:
    blocks = []
    for i, c in enumerate(contexts, start=1):
        blocks.append(
            f"[CTX {i}]\n"
            f"document_id: {c.document_id}\n"
            f"chunk_id: {c.id}\n"
            f"score: {float(c.score):.4f}\n"
            f"text:\n{c.text}\n"
        )

    joined = "\n\n".join(blocks)

    return f"""
You must answer the question using ONLY the context blocks provided.
If the context lacks enough evidence, set unknown=true and answer that you don't know.

Return ONLY a valid JSON object with this schema:
{{
  "answer": string,
  "unknown": boolean,
  "citations": [{{"document_id": string, "chunk_id": string, "snippet": string}}],
  "followups": [string]
}}

Rules:
- If unknown=true: citations must be [].
- If unknown=false: include 1-5 citations.
- Each citation snippet MUST be an exact excerpt from its cited context block text.
- Do NOT invent document_id or chunk_id.

Question:
{query}

Context blocks:
{joined}
""".strip()


def run_rag(workspace_id: str, query: str, contexts: list[RetrievedChunk]) -> tuple[GenOut, int]:
    """Run generation with trace persistence and latency measurement."""
    with timer(GEN_LATENCY):
        t0 = time.time()
        prompt = build_prompt(query, contexts)
        try:
            raw = generate(prompt).strip()
        except Exception as e:  # provider/network/model errors
            raise GenerationFailure("llm_provider_error", f"LLM provider error: {type(e).__name__}: {e}")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise GenerationFailure("invalid_json", "LLM output is not JSON")
            try:
                data = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                raise GenerationFailure("invalid_json", "LLM output is not JSON")

        try:
            out = GenOut.model_validate(data)
        except ValidationError as e:
            raise GenerationFailure("schema_validation", f"LLM output failed schema validation: {e}")

        latency_ms = int((time.time() - t0) * 1000)
        persist_trace(
            trace_type="generation",
            workspace_id=workspace_id,
            body={
                "query": query,
                "unknown": out.unknown,
                "citations": [c.model_dump() for c in out.citations],
                "answer": out.answer,
            },
            latency_ms=latency_ms,
        )
        return out, latency_ms


def run_rag_safe(workspace_id: str, query: str, contexts: list[RetrievedChunk]) -> tuple[GenOut, int, str | None]:
    """Reliability-hardened wrapper around run_rag.

    - Converts failures into an *unknown=true* response (safe degradation).
    - Persists a failure trace with a taxonomy code for offline analysis.
    """
    t0 = time.time()
    try:
        out, latency_ms = run_rag(workspace_id, query, contexts)
        return out, latency_ms, None
    except GenerationFailure as e:
        GEN_FAILURES.labels(code=e.code).inc()
        latency_ms = int((time.time() - t0) * 1000)
        persist_trace(
            trace_type="generation_failure",
            workspace_id=workspace_id,
            body={
                "query": query,
                "code": e.code,
                "message": str(e),
            },
            latency_ms=latency_ms,
        )
        return GenOut(answer="I don’t know based on the provided context.", unknown=True, citations=[], followups=[]), latency_ms, e.code
    except Exception as e:
        GEN_FAILURES.labels(code="unclassified").inc()
        latency_ms = int((time.time() - t0) * 1000)
        persist_trace(
            trace_type="generation_failure",
            workspace_id=workspace_id,
            body={
                "query": query,
                "code": "unclassified",
                "message": f"{type(e).__name__}: {e}",
            },
            latency_ms=latency_ms,
        )
        return GenOut(answer="I don’t know based on the provided context.", unknown=True, citations=[], followups=[]), latency_ms, "unclassified"
