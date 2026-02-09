from __future__ import annotations

from sqlalchemy import text

from app.core.config import settings
from app.schemas import RetrievedChunk
from app.data.db import session_scope


class LexicalRetriever:
    """Postgres Full-Text Search retriever.

    This models a sparse/BM25-like first-stage retriever (without extra infra).
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
        sql = text(
            """
            WITH q AS (SELECT plainto_tsquery('english', :q) AS query)
            SELECT
              c.id::text AS id,
              c.document_id::text AS document_id,
              c.chunk_index AS chunk_index,
              c.chunk_text AS chunk_text,
              ts_rank_cd(to_tsvector('english', c.chunk_text), q.query) AS score
            FROM document_chunk c
            JOIN document d ON d.id = c.document_id
            CROSS JOIN q
            WHERE d.workspace_id = :workspace_id
              AND c.embedding_version = :embedding_version
              AND to_tsvector('english', c.chunk_text) @@ q.query
            ORDER BY score DESC
            LIMIT :k
            """
        )

        with session_scope(database_url) as db:
            db.execute(text("SET LOCAL statement_timeout = :ms"), {"ms": int(settings.retriever_timeout_ms)})
            rows = db.execute(sql, {"q": query, "workspace_id": workspace_id, "k": int(k), "embedding_version": (embedding_version or settings.embedding_version)}).mappings().all()

        out: list[RetrievedChunk] = []
        for r in rows:
            out.append(
                RetrievedChunk(
                    id=r["id"],
                    document_id=r["document_id"],
                    chunk_index=r.get("chunk_index"),
                    text=r["chunk_text"],
                    score=float(r.get("score") or 0.0),
                    meta={"retriever": "lexical", "embedding_version": (embedding_version or settings.embedding_version)},
                )
            )
        return out
