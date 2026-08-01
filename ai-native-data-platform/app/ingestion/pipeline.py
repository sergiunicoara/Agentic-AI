from __future__ import annotations

import hashlib
import threading
import uuid

from sqlalchemy import text

from app.core.config import settings
from app.core.observability import INGEST_JOBS, INGEST_LATENCY, emit_event, timer
from app.data.db import workspace_session_scope
from app.chunking import chunk_text
from app.providers.embeddings import embed

def _opensearch_dual_write_batch(chunk_payloads: list[dict]) -> None:
    """Best-effort batched dual-write to OpenSearch.

    Called AFTER the Postgres transaction commits, so OpenSearch never sees
    chunks from a rolled-back transaction and a slow OpenSearch never holds
    a Postgres connection open. Never raises — failures are logged only;
    divergence is repaired by backfill, not by failing ingestion.
    """
    if not chunk_payloads:
        return
    if not settings.opensearch_dual_write or not settings.opensearch_url:
        return
    try:
        from app.opensearch.client import is_available
        from app.opensearch.ingest import bulk_upsert
        if not is_available():
            return
        bulk_upsert(chunk_payloads)
    except Exception as e:
        emit_event(
            "opensearch_dual_write_failed",
            {"chunks": len(chunk_payloads), "error": str(e)},
        )
_started = False


def enqueue(document_id: str, workspace_id: str) -> None:
    from app.ingestion.jobs import enqueue_document
    enqueue_document(document_id, workspace_id)


def start_worker() -> None:
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_loop, daemon=True, name="durable-ingestion-worker")
    t.start()


def _loop() -> None:
    from app.ingestion.jobs import IngestionJob, run_forever
    from app.ingestion.multimodal import process_images

    def _handle(job: IngestionJob) -> None:
        try:
            if job.job_type == "document" and job.document_id:
                process_document(job.document_id, job.workspace_id)
            elif job.job_type == "image":
                process_images(
                    workspace_id=job.workspace_id,
                    source_name=str(job.payload.get("source_name") or "upload"),
                    images=job.media,
                    external_id=job.payload.get("external_id"),
                    document_id=job.document_id,
                )
            else:
                raise ValueError(f"unsupported ingestion job type: {job.job_type}")
        except Exception as exc:
            emit_event("ingest_failed", {"job_id": job.id, "job_type": job.job_type, "error": str(exc)})
            raise

    run_forever(_handle)


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def process_document(document_id: str, workspace_id: str) -> None:
    """Idempotent ingestion run: chunk, embed, and persist.

    Demonstrates platform concerns:
    - idempotency via (document_id, chunk_index, embedding_version)
    - content-hash dedupe for operational efficiency
    - traceability via ingestion_run metadata
    """

    run_id = str(uuid.uuid4())
    with workspace_session_scope(workspace_id, write=True) as db:
        db.execute(
            text(
                """
                INSERT INTO ingestion_run (id, document_id, workspace_id, status, embedding_version)
                VALUES (:id, :doc, :workspace_id, 'running', :v)
                """
            ),
            {"id": run_id, "doc": document_id, "workspace_id": workspace_id, "v": settings.embedding_version},
        )

    with timer(INGEST_LATENCY):
        try:
            os_payloads: list[dict] = []
            with workspace_session_scope(workspace_id, write=True) as db:
                doc = db.execute(
                    text("SELECT id::text, workspace_id, source_name, text FROM document WHERE id=CAST(:id AS uuid)"),
                    {"id": document_id},
                ).mappings().first()
                if not doc:
                    raise ValueError("document not found")

                chunks = chunk_text(doc["text"])

                ws = str(doc.get("workspace_id"))
                source = str(doc.get("source_name") or "upload")
                for idx, ch in enumerate(chunks):
                    chash = _hash_text(ch)
                    v = embed(ch)
                    # RETURNING tells us whether this row was actually inserted.
                    # On conflict (re-ingestion) Postgres keeps the existing row
                    # and its existing id — we must NOT push a new id to
                    # OpenSearch, or the two stores diverge.
                    inserted = db.execute(
                        text(
                            """
                            INSERT INTO document_chunk (id, document_id, workspace_id, chunk_index, chunk_text, chunk_hash, embedding, embedding_version)
                            VALUES (:id, :document_id, :workspace_id, :chunk_index, :chunk_text, :chunk_hash, CAST(:embedding AS vector), :embedding_version)
                            ON CONFLICT (document_id, chunk_index, embedding_version) DO NOTHING
                            RETURNING id::text
                            """
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "document_id": document_id,
                            "workspace_id": ws,
                            "chunk_index": idx,
                            "chunk_text": ch,
                            "chunk_hash": chash,
                            "embedding": _vec_literal(v),
                            "embedding_version": settings.embedding_version,
                        },
                    ).first()
                    if inserted:
                        os_payloads.append({
                            "chunk_id": inserted[0],
                            "document_id": document_id,
                            "workspace_id": ws,
                            "chunk_index": idx,
                            "content": ch,
                            "embedding": v,
                            "source": source,
                            "embedding_version": settings.embedding_version,
                        })

                db.execute(
                    text("UPDATE ingestion_run SET status='success', finished_at=now() WHERE id=:id"),
                    {"id": run_id},
                )

            # Dual-write only after the Postgres transaction has committed.
            _opensearch_dual_write_batch(os_payloads)

            # Bump epoch so the retrieval cache is invalidated for this workspace.
            from app.indexing.index_state import bump_index_epoch
            bump_index_epoch(ws)

            INGEST_JOBS.labels(status="success").inc()

        except Exception as e:
            with workspace_session_scope(workspace_id, write=True) as db:
                db.execute(
                    text("UPDATE ingestion_run SET status='failed', error=:err, finished_at=now() WHERE id=:id"),
                    {"id": run_id, "err": str(e)},
                )
            INGEST_JOBS.labels(status="failed").inc()
            raise
