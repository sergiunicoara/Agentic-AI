from __future__ import annotations

from sqlalchemy import text

from app.core.config import settings
from app.data.db import session_scope
from app.schemas import RetrievedChunk


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


class MultimodalDenseRetriever:
    """Dense retrieval unified across text chunks and image chunks.

    Queries both document_chunk and image_chunk tables in a single UNION,
    re-ranks by cosine similarity, and annotates each result with its modality
    so downstream rerankers and citation verifiers can handle text/image
    results correctly.
    """

    def retrieve(
        self,
        workspace_id: str,
        query: str,
        k: int,
        *,
        query_vec: list[float] | None = None,
        database_url: str | None = None,
        embedding_version: str | None = None,
    ) -> list[RetrievedChunk]:
        from app.providers.embeddings import embed

        qvec = query_vec or embed(query)
        qlit = _vec_literal(qvec)
        ev = embedding_version or settings.embedding_version

        sql = text(
            """
            SELECT
              id,
              document_id,
              chunk_index,
              chunk_text  AS content,
              (1 - (embedding <=> :qvec::vector)) AS score,
              'text'      AS modality,
              NULL        AS caption
            FROM document_chunk
            WHERE workspace_id = :workspace_id
              AND embedding_version = :ev

            UNION ALL

            SELECT
              id,
              document_id,
              page_number AS chunk_index,
              caption     AS content,
              (1 - (embedding <=> :qvec::vector)) AS score,
              'image'     AS modality,
              caption
            FROM image_chunk
            WHERE workspace_id = :workspace_id
              AND embedding_version = :ev

            ORDER BY score DESC
            LIMIT :k
            """
        )

        with session_scope(database_url) as db:
            db.execute(
                text("SET LOCAL statement_timeout = :ms"),
                {"ms": int(settings.retriever_timeout_ms)},
            )
            rows = db.execute(
                sql,
                {"qvec": qlit, "workspace_id": workspace_id, "ev": ev, "k": k},
            ).mappings().all()

        return [
            RetrievedChunk(
                id=str(r["id"]),
                document_id=str(r["document_id"]) if r["document_id"] else "",
                chunk_index=r.get("chunk_index"),
                text=r["content"],
                score=float(r.get("score") or 0.0),
                modality=r["modality"],
                caption=r.get("caption"),
                meta={
                    "retriever": "multimodal_dense",
                    "embedding_version": ev,
                    "modality": r["modality"],
                },
            )
            for r in rows
        ]
