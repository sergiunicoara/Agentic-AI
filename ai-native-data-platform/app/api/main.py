from __future__ import annotations

import hmac
import time
import uuid
import asyncio

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

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
from app.core.config import settings
from app.core.exp.router import choose_experiment
from app.core.reliability.slo_window import rolling_slo
from app.core.reliability.anomaly import observe_slo_signals
from app.core.reliability.remediation_controller import start_controller as start_remediation_controller
from app.data.db import read_session_scope, workspace_session_scope
from app.eval.service import compute_online_signals
from app.generation.groundedness import evidence_minimum, verify_citation_snippets
from app.generation.service import run_rag_safe
from app.providers.embeddings import embed
from app.retrieval.factory import build_pipeline
from app.schemas import AskIn, AskOut, Citation, ImageIngestOut, NLQueryIn, NLQueryOut, TranscriptIn
from app.nl_query.service import NLQueryError, run_nl_query
from app.ingestion.pipeline import enqueue
from app.ingestion.multimodal import PdfTooManyPagesError, enqueue_images, pdf_to_images
from app.core.safety.prompt_guard import check_query
from app.core.safety.output_moderation import moderate_output


configure_logging()

app = FastAPI(title="AI-Native Data Platform (AI-native RAG platform scaffold)")

_semaphore = asyncio.Semaphore(settings.max_in_flight_requests)
contract = default_contract()


@app.on_event("startup")
def _startup():
    if settings.enable_auto_remediation:
        # Only one API replica becomes leader and applies mitigation.
        start_remediation_controller()


@app.middleware("http")
async def metrics_middleware(request, call_next):
    route = request.url.path
    method = request.method
    # Backpressure: cap in-flight requests and shed load early. Per-workspace
    # rate limiting happens later, inside require_workspace_key (app/auth.py)
    # — it must run *after* credentials are validated. Enforcing it here,
    # keyed off the unauthenticated X-Workspace-Id header, would let anyone
    # drain a real workspace's quota with a forged header and no valid key.
    async with _semaphore:
        with HTTP_LATENCY.labels(route=route, method=method).time():
            resp = await call_next(request)
    HTTP_REQUESTS.labels(route=route, method=method, status=str(resp.status_code)).inc()
    return resp


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    """Liveness: is this process alive and able to handle a request.

    Deliberately checks nothing external. k8s/api-deployment.yaml's
    livenessProbe restarts the pod on failure — that's the right response
    to "this process is wedged," but restarting is useless (and actively
    harmful) against "Postgres is down," since it fixes nothing and, done
    across every replica during a real outage, turns one dependency outage
    into a full restart storm. See /health/ready for the dependency check.
    """
    return {"ok": True}


@app.get("/health/ready")
def health_ready():
    """Readiness: should this pod currently receive traffic.

    Postgres is a hard dependency — essentially nothing on this API works
    without it (auth, retrieval, generation tracing), so unreachable here
    means not ready. Redis and OpenSearch are deliberately NOT checked the
    same way: both are designed elsewhere in this app to degrade
    gracefully when unavailable (cache.py falls back to an in-process LRU,
    OpenSearch dual-write is best-effort) — reported for visibility, but
    their being down doesn't pull the pod out of rotation.
    """
    checks: dict[str, str] = {}
    ok = True

    try:
        with read_session_scope() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"unreachable: {type(e).__name__}: {e}"
        ok = False

    if settings.redis_url:
        # local import to keep FastAPI startup light, matching /ask below
        from app.core.cache import cache
        try:
            if cache._redis is None:
                raise RuntimeError("not connected")
            cache._redis.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"unreachable (degrades to in-process cache): {type(e).__name__}: {e}"

    if settings.opensearch_url:
        from app.opensearch.client import is_available as opensearch_is_available
        checks["opensearch"] = "ok" if opensearch_is_available() else "unreachable (dual-write degrades to Postgres-only)"

    return JSONResponse({"ok": ok, "checks": checks}, status_code=200 if ok else 503)


@app.post("/ingest/transcript")
def ingest_transcript(payload: TranscriptIn, workspace_id: str = Depends(require_workspace_key)):
    if payload.workspace_id != workspace_id:
        raise HTTPException(403, "Workspace mismatch")

    doc_id = str(uuid.uuid4())
    try:
        # The document insert and its ingestion_job enqueue share this one
        # transaction (both use `db`) so they commit or roll back together.
        # Doing them as two separate transactions left a real gap: if the
        # process died (or the enqueue insert itself failed) between them,
        # the document existed but was never queued for processing — and
        # re-POSTing the same transcript just returned "already_ingested"
        # forever, since the document row was already there.
        with workspace_session_scope(payload.workspace_id, write=True) as db:
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
            enqueue(doc_id, payload.workspace_id, db=db)
    except IntegrityError:
        with workspace_session_scope(payload.workspace_id) as db:
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

    emit_event("ingest_enqueued", {"document_id": doc_id, "workspace_id": payload.workspace_id})
    return {"status": "queued", "document_id": doc_id}


@app.post("/ingest/image", response_model=ImageIngestOut)
async def ingest_image(
    file: UploadFile = File(...),
    workspace_id: str = Depends(require_workspace_key),
    source: str = Form(default="upload"),
    external_id: str | None = Form(default=None),
):
    """Multimodal ingestion: accepts an image (PNG/JPG) or PDF file.

    PDF pages are converted to images; each page/image is captioned by the
    configured vision model (GPT-4o / Gemini Vision / mock), embedded, and
    stored in image_chunk for unified retrieval alongside text chunks.
    """
    # Read in bounded chunks so an oversized upload is rejected before it's
    # fully buffered, not after (FastAPI's UploadFile.read() with no size arg
    # would happily pull the entire body into memory first).
    max_bytes = settings.max_image_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1_048_576)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, f"Upload exceeds max size of {max_bytes} bytes")
        chunks.append(chunk)
    content = b"".join(chunks)
    mime = file.content_type or "image/png"

    if mime == "application/pdf" or (file.filename or "").lower().endswith(".pdf"):
        # pdf2image shells out to poppler and rasterizes every page — real
        # CPU work, not I/O. Running it inline on this async handler would
        # block the event loop (and therefore every other concurrent
        # request this process is serving) for however long that takes.
        try:
            images = await run_in_threadpool(pdf_to_images, content)
        except PdfTooManyPagesError as e:
            raise HTTPException(413, str(e))
    else:
        images = [(content, mime)]

    job_id = enqueue_images(
        workspace_id,
        source or file.filename or "upload",
        images,
        external_id=external_id,
    )
    emit_event("multimodal_ingest_enqueued", {"workspace_id": workspace_id, "page_count": len(images), "job_id": job_id})
    return ImageIngestOut(status="queued", page_count=len(images))


@app.post("/ask", response_model=AskOut)
def ask(payload: AskIn, request: Request, workspace_id: str = Depends(require_workspace_key)):
    if payload.workspace_id != workspace_id:
        raise HTTPException(403, "Workspace mismatch")

    t0 = time.time()

    # Prompt injection guard — scan the query before it reaches any LLM prompt.
    guard = check_query(payload.query)
    if not guard.safe:
        emit_event("prompt_injection_blocked", {"workspace_id": workspace_id, "reason": guard.reason})
        raise HTTPException(400, f"Query rejected: {guard.reason}")

    # Admin-only overrides (canary embedding version, forced experiment) share
    # one token check. Without gating X-Experiment specifically: any caller
    # could pick their own retrieval pipeline directly — including opting
    # back into an experiment the remediation controller has just forced
    # traffic away from over an SLO violation, defeating the point of that
    # automated safety override — and each distinct header value would also
    # occupy a slot in build_pipeline's lru_cache(maxsize=32), a cheap way to
    # evict legitimately-cached pipelines under churn.
    is_admin = bool(
        settings.admin_token
        and hmac.compare_digest(request.headers.get("X-Admin-Token", ""), settings.admin_token)
    )

    # A/B retrieval experiment routing.
    # - X-Experiment force-selects a pipeline (debugging/analysis) when
    #   allow_experiment_override is on and the caller is an admin.
    # - otherwise stable percentage rollout chooses treatment
    requested_experiment = request.headers.get("X-Experiment") if (settings.allow_experiment_override and is_admin) else None
    assignment = choose_experiment(payload.workspace_id, requested=requested_experiment)
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
    embedding_override = request.headers.get("X-Embedding-Version-Override") if (settings.allow_embedding_override and is_admin) else None

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
    except ReliabilityViolation:
        # Reliability violations intentionally degrade to safe fallback behavior.
        return AskOut(answer="I don’t know based on the indexed documents in this workspace.", citations=[], unknown=True)
    except Exception as e:
        # A raw infra failure (DB statement timeout, OpenSearch connection
        # error, etc.) must degrade the same way a ReliabilityViolation
        # does — this whole endpoint is built around "unknown" being the
        # safe fallback, not an HTTP 500. Distinguished from the branch
        # above via the emitted event so an actual outage doesn't read as
        # a routine reliability-contract degradation in the logs.
        emit_event(
            "ask_retrieval_failed",
            {"workspace_id": payload.workspace_id, "error": f"{type(e).__name__}: {e}"},
        )
        return AskOut(answer="I don’t know based on the indexed documents in this workspace.", citations=[], unknown=True)

    # Simple confidence gate: scale-aware signal; swap for calibrated thresholds per workspace.
    top_score = float(hits[0].score) if hits else 0.0
    distinct_docs = len({h.document_id for h in hits})
    # RRF-fused scores compress to 1/(k+rank) ≈ 0.016; raw BM25/cosine scores
    # are in 0–1+. Gate on presence of hits rather than a fixed score threshold.
    low_confidence = (len(hits) == 0) or (distinct_docs < 1)

    # Always defined (not just in the generation branch below) so the SLO
    # observation further down doesn't need a locals()-sniffing fallback to
    # tell "no generation attempted" apart from "generation attempted and
    # succeeded" — both are simply gen_err is None.
    gen_err: str | None = None

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
            ok2, _reason2 = evidence_minimum([c.model_dump() for c in citations], min_chars=40)

            groundedness = 1.0 if (ok and ok2) else 0.0
            try:
                enforce_groundedness(groundedness, contract)
            except ReliabilityViolation:
                # Online guardrail: degrade to unknown rather than returning
                # potentially ungrounded output.
                answer = "I don’t know based on the provided context."
                citations = []
                unknown = True

        if not unknown:
            # Output moderation — PII redaction + toxicity gate.
            moderation = moderate_output(answer)
            if not moderation.safe:
                emit_event("output_moderation_blocked", {"workspace_id": workspace_id, "flags": moderation.flags})
                answer = "I don’t know based on the provided context."
                citations = []
                unknown = True
            elif moderation.redacted is not None:
                emit_event("output_pii_redacted", {"workspace_id": workspace_id, "flags": moderation.flags})
                answer = moderation.redacted

        if not unknown and citations:
            # Citation snippets are raw excerpts from retrieved content and can
            # carry the same PII the answer redaction above just handled — the
            # answer being clean doesn't mean the quoted source text is.
            safe_citations: list[Citation] = []
            citation_redacted = False
            for c in citations:
                cmod = moderate_output(c.snippet)
                if not cmod.safe:
                    # Drop the individual toxic citation rather than discarding
                    # the whole (already-verified, grounded) answer over it.
                    continue
                if cmod.redacted is not None:
                    citation_redacted = True
                    safe_citations.append(c.model_copy(update={"snippet": cmod.redacted}))
                else:
                    safe_citations.append(c)
            if citation_redacted:
                emit_event("citation_pii_redacted", {"workspace_id": workspace_id})
            citations = safe_citations

    latency_ms = int((time.time() - t0) * 1000)
    try:
        # The online contract applies to the complete user-visible path, not
        # merely the retrieval stage — but it uses its own, larger budget
        # (max_end_to_end_latency_ms), not the retrieval-only ceiling
        # already enforced above. Reusing the retrieval ceiling here would
        # count real LLM generation time against a budget sized for
        # retrieval alone, silently discarding every real (non-mock) answer
        # that takes longer than that to generate.
        enforce_latency(latency_ms, contract, threshold_ms=contract.max_end_to_end_latency_ms)
    except ReliabilityViolation:
        answer = "I don't know based on the indexed documents in this workspace."
        citations = []
        unknown = True

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
        is_error=bool(gen_err),
        is_unknown=bool(unknown),
    )
    snap = rolling_slo.snapshot()
    scores = observe_slo_signals(snap["p95_latency_ms"], snap["error_rate"], snap["unknown_rate"])
    if max(scores.values()) >= 6.0:
        emit_event("anomaly_detected", {"scores": scores, "snapshot": snap, "workspace_id": payload.workspace_id})

    return AskOut(answer=answer, citations=citations, unknown=unknown)


@app.post("/query/natural-language", response_model=NLQueryOut)
def natural_language_query(payload: NLQueryIn, workspace_id: str = Depends(require_workspace_key)):
    """NLP → JSON → SQL pipeline.

    Accepts a plain-English question, extracts a structured QueryIntent via
    PydanticAI, builds a validated parameterized SQL query, executes it on
    PostgreSQL (workspace-scoped), and returns results with the generated SQL
    for transparency. Every query is written to nl_query_audit_log.
    """
    if payload.workspace_id != workspace_id:
        raise HTTPException(403, "Workspace mismatch")

    try:
        result = run_nl_query(payload.query, workspace_id)
    except NLQueryError as e:
        raise HTTPException(e.status_code, e.message)

    return NLQueryOut(**result)
