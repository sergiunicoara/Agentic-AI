from __future__ import annotations

import hashlib
import io
import queue
import threading
import uuid
from dataclasses import dataclass, field

from sqlalchemy import text

from app.core.config import settings
from app.core.observability import INGEST_JOBS, emit_event
from app.data.db import write_session_scope
from app.providers.embeddings import embed
from app.providers.vision import caption_image

_mm_jobs: "queue.Queue[_ImageJob]" = queue.Queue()
_started = False


@dataclass
class _ImageJob:
    workspace_id: str
    source_name: str
    images: list[tuple[bytes, str]]  # (image_bytes, mime_type)
    external_id: str | None = None
    document_id: str | None = None  # parent document, set when source is a PDF document


def enqueue_images(
    workspace_id: str,
    source_name: str,
    images: list[tuple[bytes, str]],
    *,
    external_id: str | None = None,
    document_id: str | None = None,
) -> None:
    _mm_jobs.put(_ImageJob(workspace_id, source_name, images, external_id, document_id))


def start_multimodal_worker() -> None:
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def _loop() -> None:
    while True:
        job = _mm_jobs.get()
        try:
            _process_job(job)
        except Exception as e:
            emit_event("multimodal_ingest_failed", {"source": job.source_name, "error": str(e)})
        finally:
            _mm_jobs.task_done()


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def _process_job(job: _ImageJob) -> None:
    for page_number, (img_bytes, mime_type) in enumerate(job.images):
        image_hash = _hash_bytes(img_bytes)

        # Content-hash dedup — skip if already indexed for this workspace.
        with write_session_scope() as db:
            existing = db.execute(
                text(
                    "SELECT id FROM image_chunk "
                    "WHERE image_hash = :h AND workspace_id = :w LIMIT 1"
                ),
                {"h": image_hash, "w": job.workspace_id},
            ).first()
        if existing:
            continue

        # Vision model → caption → embed caption for retrieval.
        caption = caption_image(img_bytes, mime_type)
        embedding = embed(caption)

        with write_session_scope() as db:
            db.execute(
                text(
                    """
                    INSERT INTO image_chunk
                      (id, workspace_id, document_id, source_name, external_id,
                       page_number, caption, embedding, embedding_version, image_hash)
                    VALUES
                      (:id, :workspace_id, :document_id, :source_name, :external_id,
                       :page_number, :caption, CAST(:embedding AS vector), :embedding_version, :image_hash)
                    ON CONFLICT (image_hash, workspace_id) DO NOTHING
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "workspace_id": job.workspace_id,
                    "document_id": job.document_id,
                    "source_name": job.source_name,
                    "external_id": job.external_id,
                    "page_number": page_number,
                    "caption": caption,
                    "embedding": _vec_literal(embedding),
                    "embedding_version": settings.embedding_version,
                    "image_hash": image_hash,
                },
            )

        INGEST_JOBS.labels(status="success").inc()
        emit_event(
            "image_chunk_ingested",
            {"workspace_id": job.workspace_id, "source": job.source_name, "page": page_number},
        )


def pdf_to_images(pdf_bytes: bytes) -> list[tuple[bytes, str]]:
    """Convert each PDF page to a PNG image for visual ingestion."""
    from pdf2image import convert_from_bytes

    pages = convert_from_bytes(pdf_bytes, dpi=150, fmt="PNG")
    result = []
    for page in pages:
        buf = io.BytesIO()
        page.save(buf, format="PNG")
        result.append((buf.getvalue(), "image/png"))
    return result
