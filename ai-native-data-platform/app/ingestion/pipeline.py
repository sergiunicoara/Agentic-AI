from __future__ import annotations

import hashlib
import queue
import threading
import time
import uuid

from sqlalchemy import text

from app.core.config import settings
from app.core.observability import INGEST_JOBS, INGEST_LATENCY, emit_event, timer
from app.data.db import write_session_scope
from app.chunking import chunk_text
from app.providers.embeddings import embed

_jobs: "queue.Queue[str]" = queue.Queue()


def _opensearch_dual_write(
    *,
    chunk_id: str,
    document_id: str,
    workspace_id: str,
    chunk_index: int,
    content: str,
    embedding: list[float],
    source: str,
    embedding_version: str,
) -> None:
    """Best-effort dual-write to OpenSearch. Never raises — failures are logged only."""
    if not settings.opensearch_dual_write or not settings.opensearch_url:
        return
    try:
        from app.opensearch.client import is_available
        from app.opensearch.ingest import upsert_chunk
        if not is_available():
            return
        upsert_chunk(
            chunk_id=chunk_id,
            document_id=document_id,
            workspace_id=workspace_id,
            chunk_index=chunk_index,
            content=content,
            embedding=embedding,
            source=source,
            embedding_version=embedding_version,
        )
    except Exception as e:
        emit_event("opensearch_dual_write_failed", {"chunk_id": chunk_id, "error": str(e)})
_started = False


def enqueue(document_id: str) -> None:
    _jobs.put(document_id)


def start_worker() -> None:
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def _loop() -> None:
    while True:
        doc_id = _jobs.get()
        try:
            process_document(doc_id)
        except Exception as e:
            emit_event("ingest_failed", {"document_id": doc_id, "error": str(e)})
        finally:
            _jobs.task_done()


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def process_document(document_id: str) -> None:
    """Idempotent ingestion run: chunk, embed, and persist.

    Demonstrates platform concerns:
    - idempotency via (document_id, chunk_index, embedding_version)
    - content-hash dedupe for operational efficiency
    - traceability via ingestion_run metadata
    """

    run_id = str(uuid.uuid4())
    with write_session_scope() as db:
        db.execute(
            text(
                """
                INSERT INTO ingestion_run (id, document_id, status, embedding_version)
                VALUES (:id, :doc, 'running', :v)
                """
            ),
            {"id": run_id, "doc": document_id, "v": settings.embedding_version},
        )

    with timer(INGEST_LATENCY):
        try:
            with write_session_scope() as db:
                doc = db.execute(
                    text("SELECT id::text, workspace_id, text FROM document WHERE id=:id"),
                    {"id": document_id},
                ).mappings().first()
                if not doc:
                    raise ValueError("document not found")

                chunks = chunk_text(doc["text"])

                ws = str(doc.get("workspace_id"))
                source = str(doc.get("source_name", "upload"))
                for idx, ch in enumerate(chunks):
                    chash = _hash_text(ch)
                    v = embed(ch)
                    chunk_id = str(uuid.uuid4())
                    db.execute(
                        text(
                            """
                            INSERT INTO document_chunk (id, document_id, workspace_id, chunk_index, chunk_text, chunk_hash, embedding, embedding_version)
                            VALUES (:id, :document_id, :workspace_id, :chunk_index, :chunk_text, :chunk_hash, CAST(:embedding AS vector), :embedding_version)
                            ON CONFLICT (document_id, chunk_index, embedding_version) DO NOTHING
                            """
                        ),
                        {
                            "id": chunk_id,
                            "document_id": document_id,
                            "workspace_id": ws,
                            "chunk_index": idx,
                            "chunk_text": ch,
                            "chunk_hash": chash,
                            "embedding": _vec_literal(v),
                            "embedding_version": settings.embedding_version,
                        },
                    )
                    # Dual-write to OpenSearch — fire-and-forget, never blocks Postgres tx
                    _opensearch_dual_write(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        workspace_id=ws,
                        chunk_index=idx,
                        content=ch,
                        embedding=v,
                        source=source,
                        embedding_version=settings.embedding_version,
                    )

                db.execute(
                    text("UPDATE ingestion_run SET status='success', finished_at=now() WHERE id=:id"),
                    {"id": run_id},
                )

            INGEST_JOBS.labels(status="success").inc()

        except Exception as e:
            with write_session_scope() as db:
                db.execute(
                    text("UPDATE ingestion_run SET status='failed', error=:err, finished_at=now() WHERE id=:id"),
                    {"id": run_id, "err": str(e)},
                )
            INGEST_JOBS.labels(status="failed").inc()
            raise
