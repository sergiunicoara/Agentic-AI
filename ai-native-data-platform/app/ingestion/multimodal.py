from __future__ import annotations

import hashlib
import io
import uuid

from sqlalchemy import text

from app.core.config import settings
from app.core.observability import INGEST_JOBS, emit_event
from app.data.db import workspace_session_scope
from app.providers.embeddings import embed
from app.providers.vision import caption_image

def enqueue_images(
    workspace_id: str,
    source_name: str,
    images: list[tuple[bytes, str]],
    *,
    external_id: str | None = None,
    document_id: str | None = None,
) -> str:
    from app.ingestion.jobs import enqueue_images as enqueue_durable_images

    return enqueue_durable_images(
        workspace_id,
        source_name,
        images,
        external_id=external_id,
        document_id=document_id,
    )


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def process_images(
    *,
    workspace_id: str,
    source_name: str,
    images: list[tuple[bytes, str]],
    external_id: str | None = None,
    document_id: str | None = None,
) -> None:
    # See app/ingestion/pipeline.py::process_document for why this must be
    # the workspace's active embedding version, not settings.embedding_version.
    from app.indexing.index_state import get_index_state
    embedding_version = get_index_state(workspace_id).active_embedding_version

    for page_number, (img_bytes, mime_type) in enumerate(images):
        image_hash = _hash_bytes(img_bytes)

        # Content-hash dedup — skip if already indexed for this workspace.
        with workspace_session_scope(workspace_id, write=True) as db:
            existing = db.execute(
                text(
                    "SELECT id FROM image_chunk "
                    "WHERE image_hash = :h AND workspace_id = :w LIMIT 1"
                ),
                {"h": image_hash, "w": workspace_id},
            ).first()
        if existing:
            continue

        # Vision model → caption → embed caption for retrieval.
        caption = caption_image(img_bytes, mime_type)
        embedding = embed(caption)

        with workspace_session_scope(workspace_id, write=True) as db:
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
                    "workspace_id": workspace_id,
                    "document_id": document_id,
                    "source_name": source_name,
                    "external_id": external_id,
                    "page_number": page_number,
                    "caption": caption,
                    "embedding": _vec_literal(embedding),
                    "embedding_version": embedding_version,
                    "image_hash": image_hash,
                },
            )

        INGEST_JOBS.labels(status="success").inc()
        emit_event(
            "image_chunk_ingested",
            {"workspace_id": workspace_id, "source": source_name, "page": page_number},
        )


class PdfTooManyPagesError(ValueError):
    """Raised when an uploaded PDF exceeds settings.max_pdf_pages."""

    def __init__(self, page_count: int, limit: int):
        self.page_count = page_count
        self.limit = limit
        super().__init__(f"PDF has {page_count} pages, exceeding the limit of {limit}")


def pdf_to_images(pdf_bytes: bytes) -> list[tuple[bytes, str]]:
    """Convert each PDF page to a PNG image for visual ingestion.

    Each page is a full rasterization (dpi=150) done by shelling out to
    poppler — a small page cap protects the API process from a "page bomb"
    (a tiny PDF file declaring thousands of pages) turning one upload into
    an unbounded amount of CPU/memory work and, per page, its own vision
    API call and pgvector row downstream.
    """
    from pdf2image import convert_from_bytes, pdfinfo_from_bytes

    # pdfinfo is a cheap metadata read (no rasterization) — check the page
    # count before doing any conversion work at all.
    info = pdfinfo_from_bytes(pdf_bytes)
    page_count = int(info.get("Pages") or 0)
    if page_count > settings.max_pdf_pages:
        raise PdfTooManyPagesError(page_count, settings.max_pdf_pages)

    # last_page is defense in depth in case pdfinfo and the actual
    # conversion ever disagree on page count (e.g. a malformed PDF).
    pages = convert_from_bytes(pdf_bytes, dpi=150, fmt="PNG", last_page=settings.max_pdf_pages)
    result = []
    for page in pages:
        buf = io.BytesIO()
        page.save(buf, format="PNG")
        result.append((buf.getvalue(), "image/png"))
    return result
