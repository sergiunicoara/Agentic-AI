from __future__ import annotations

import time
import uuid
import asyncio

from fastapi import Depends, FastAPI, HTTPException, Request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.responses import Response

from app.auth import require_workspace_key
from app.core.logging import configure_logging
from app.core.observability import HTTP_LATENCY, HTTP_REQUESTS, emit_event
from app.core.reliability.contracts import (
    ReliabilityViolation,
    default_contract,
    enforce_groundedness,
    enforce_latency,
    enforce_non_empty,
)
from app.core.rate_limit import rate_limiter
from app.core.config import settings
from app.core.exp.router import choose_experiment
from app.core.reliability.slo_window import rolling_slo
from app.core.reliability.anomaly import observe_slo_signals
from app.core.reliability.remediation_controller import start_controller as start_remediation_controller
from app.data.db import read_session_scope, write_session_scope
from app.eval.service import compute_online_signals
from app.generation.groundedness import evidence_minimum, verify_citation_snippets
from app.generation.service import run_rag_safe
from app.providers.embeddings import embed
from app.retrieval.factory import build_pipeline
from app.schemas import AskIn, AskOut, Citation, TranscriptIn
from app.ingestion.pipeline import enqueue, start_worker


configure_logging()

app = FastAPI(title="AI-Native Data Platform (AI-native RAG platform scaffold)")

_semaphore = asyncio.Semaphore(settings.max_in_flight_requests)
contract = default_contract()


@app.on_event("startup")
def _startup():
    start_worker()
    # Leader-elected automated remediation controller (portfolio feature).
    # Only one API replica becomes leader and applies mitigation.
    start_remediation_controller()


@app.middleware("http")
async def metrics_middleware(request, call_next):
    route = request.url.path
    method = request.method
    # Backpressure: cap in-flight requests and shed load early.
    async with _semaphore:
        # Rate-limit per workspace if header is present.
        ws = request.headers.get("X-Workspace-Id", "")
        if ws and route in ("/ask", "/ingest/transcript"):
            if not rate_limiter.allow(ws):
                HTTP_REQUESTS.labels(route=route, method=method, status="429").inc()
                return Response(content="Rate limit exceeded", status_code=429)

        with HTTP_LATENCY.labels(route=route, method=method).time():
            resp = await call_next(request)
    HTTP_REQUESTS.labels(route=route, method=method, status=str(resp.status_code)).inc()
    return resp


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ingest/transcript")
def ingest_transcript(payload: TranscriptIn, workspace_id: str = Depends(require_workspace_key)):
    if payload.workspace_id != workspace_id:
        raise HTTPException(403, "Workspace mismatch")

    doc_id = str(uuid.uuid4())
    try:
        with write_session_scope() as db:
            db.execute(
                text(
                    """
                    INSERT INTO document (id, workspace_id, source_name, external_id, title, text)
                    VALUES (:id, :w, :s, :e, :t, :x)
                    """
                ),
                {
                    "id": doc_id,
                    "w": payload.workspace_id,
                    "s": payload.source,
                    "e": payload.external_id,
                    "t": payload.title,
                    "x": payload.text,
                },
            )
    except IntegrityError:
        with read_session_scope(region=settings.region) as db:
            row = db.execute(
                text(
                    """
                    SELECT id::text FROM document
                    WHERE workspace_id=:w AND source_name=:s AND external_id=:e
                    """
                ),
                {"w": payload.workspace_id, "s": payload.source, "e": payload.external_id},
            ).mappings().first()
        return {"status": "already_ingested", "document_id": row["id"] if row else None}

    enqueue(doc_id)
    emit_event("ingest_enqueued", {"document_id": doc_id, "workspace_id": payload.workspace_id})
    return {"status": "queued", "document_id": doc_id}


@app.post("/ask", response_model=AskOut)
def ask(payload: AskIn, request: Request, workspace_id: str = Depends(require_workspace_key)):
    if payload.workspace_id != workspace_id:
        raise HTTPException(403, "Workspace mismatch")

    t0 = time.time()

    # A/B retrieval experiment routing.
    # - X-Experiment allows explicit selection (debugging/analysis)
    # - otherwise stable percentage rollout chooses treatment
    assignment = choose_experiment(payload.workspace_id, requested=request.headers.get("X-Experiment"))
    pipeline = build_pipeline(assignment.name)
    emit_event(
        "experiment_assigned",
        {"workspace_id": payload.workspace_id, "experiment": assignment.name, "reason": assignment.reason},
    )

    # Embed once; reused for dense retrieval and reranking.
    # Cached to reduce provider calls at scale.
    from app.core.cache import cache  # local import to keep FastAPI startup light
    import hashlib
    # Query embedding cache key includes provider+model params to avoid cross-model contamination.
    from app.providers import embeddings as emb  # local import
    qsig = f"{payload.workspace_id}|{payload.query}|{emb.PROVIDER}|{emb.OPENAI_EMBED_MODEL}|{emb.EMBED_DIM}"
    qkey = "qembed:" + hashlib.sha256(qsig.encode("utf-8", errors="ignore")).hexdigest()[:32]
    qcached = cache.get_json(qkey)
    if isinstance(qcached, list):
        query_vec = [float(x) for x in qcached]
    else:
        query_vec = embed(payload.query)
        cache.set_json(qkey, query_vec, ttl_s=600)

    # Optional canary: force retrieval to use a specific embedding_version for this request.
    # Guarded by an admin token to avoid abuse.
    embedding_override = None
    if settings.allow_embedding_override:
        req_token = request.headers.get("X-Admin-Token", "")
        if settings.admin_token and req_token == settings.admin_token:
            embedding_override = request.headers.get("X-Embedding-Version-Override")

    try:
        hits, retrieval_ms = pipeline.run(
            payload.workspace_id,
            payload.query,
            query_vec=query_vec,
            k=payload.top_k,
            rerank_candidates=max(payload.top_k, 25),
            embedding_version_override=embedding_override,
        )
        enforce_non_empty(len(hits), contract)
        enforce_latency(retrieval_ms, contract)
    except ReliabilityViolation as e:
        # Reliability violations intentionally degrade to safe fallback behavior.
        return AskOut(answer="I don’t know based on the indexed documents in this workspace.", citations=[], unknown=True)

    # Simple confidence gate: scale-aware signal; swap for calibrated thresholds per workspace.
    top_score = float(hits[0].score) if hits else 0.0
    distinct_docs = len({h.document_id for h in hits})
    low_confidence = (top_score < 0.15) or (distinct_docs < 1)

    if low_confidence:
        answer = "I don’t know based on the indexed documents in this workspace."
        citations: list[Citation] = []
        unknown = True
        gen_ms = 0
    else:
        gen, gen_ms, gen_err = run_rag_safe(payload.workspace_id, payload.query, hits)
        answer = gen.answer
        citations = gen.citations
        unknown = gen.unknown

        if gen_err:
            emit_event(
                "generation_failed",
                {"workspace_id": payload.workspace_id, "code": gen_err},
            )

        if not unknown:
            ok, _reason = verify_citation_snippets(
                [h.model_dump() for h in hits],
                [c.model_dump() for c in citations],
            )
            ok2, _reason2 = evidence_minimum([c.model_dump() for c in citations], min_chars=80)

            groundedness = 1.0 if (ok and ok2) else 0.0
            try:
                enforce_groundedness(groundedness, contract)
            except ReliabilityViolation:
                # Online guardrail: degrade to unknown rather than returning
                # potentially ungrounded output.
                answer = "I don’t know based on the provided context."
                citations = []
                unknown = True

    latency_ms = int((time.time() - t0) * 1000)

    # Store online quality signals for debugging and offline eval sampling.
    compute_online_signals(
        workspace_id=payload.workspace_id,
        query=payload.query,
        retrieved=hits,
        unknown=unknown,
        latency_ms=latency_ms,
    )

    # Rolling aggregate SLO telemetry (used for alerting in ops/prometheus).
    rolling_slo.observe(
        latency_ms,
        is_error=bool(gen_err) if 'gen_err' in locals() else False,
        is_unknown=bool(unknown),
    )
    snap = rolling_slo.snapshot()
    scores = observe_slo_signals(snap["p95_latency_ms"], snap["error_rate"], snap["unknown_rate"])
    if max(scores.values()) >= 6.0:
        emit_event("anomaly_detected", {"scores": scores, "snapshot": snap, "workspace_id": payload.workspace_id})

    return AskOut(answer=answer, citations=citations, unknown=unknown)
