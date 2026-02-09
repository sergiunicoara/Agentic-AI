from __future__ import annotations

from sqlalchemy import text

from app.core.config import settings

from app.data.db import session_scope
from app.providers.embeddings import embed
from app.schemas import RetrievedChunk


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


class DenseRetriever:
    """pgvector dense retrieval.

    This models the typical *first-stage* retrieval in a production RAG stack.
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
        # IMPORTANT: avoid double-embedding. The retrieval pipeline computes the
        # query embedding once per request and passes it in.
        qvec = query_vec or embed(query)
        qlit = _vec_literal(qvec)

        sql = text(
            """
            SELECT
              c.id::text AS id,
              c.document_id::text AS document_id,
              c.chunk_index AS chunk_index,
              c.chunk_text AS chunk_text,
              (1 - (c.embedding <=> :qvec::vector)) AS score
            FROM document_chunk c
            JOIN document d ON d.id = c.document_id
            WHERE d.workspace_id = :workspace_id
              AND c.embedding_version = :embedding_version
            ORDER BY c.embedding <=> :qvec::vector
            LIMIT :k
            """
        )

        with session_scope(database_url) as db:
            # Enforce a hard ceiling at the database level to protect tail
            # latency and reduce queueing under overload.
            db.execute(text("SET LOCAL statement_timeout = :ms"), {"ms": int(settings.retriever_timeout_ms)})
            rows = db.execute(
                sql,
                {
                    "qvec": qlit,
                    "workspace_id": workspace_id,
                    "k": int(k),
                    "embedding_version": (embedding_version or settings.embedding_version),
                },
            ).mappings().all()

        out: list[RetrievedChunk] = []
        for r in rows:
            out.append(
                RetrievedChunk(
                    id=r["id"],
                    document_id=r["document_id"],
                    chunk_index=r.get("chunk_index"),
                    text=r["chunk_text"],
                    score=float(r.get("score") or 0.0),
                    meta={"retriever": "dense", "embedding_version": (embedding_version or settings.embedding_version)},
                )
            )
        return out
