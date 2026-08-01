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
                    "embedding_version": settings.embedding_version,
                    "image_hash": image_hash,
                },
            )

        INGEST_JOBS.labels(status="success").inc()
        emit_event(
            "image_chunk_ingested",
            {"workspace_id": workspace_id, "source": source_name, "page": page_number},
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
