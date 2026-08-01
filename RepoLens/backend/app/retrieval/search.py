import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.embedder import Embedder
from app.retrieval.models import RetrievedChunk
from app.tables import chunks, files

DEFAULT_TOP_K = 8
RRF_K = 60


async def search_chunks(
    session: AsyncSession,
    embedder: Embedder,
    repo_id: uuid.UUID,
    query: str,
    top_k: int = DEFAULT_TOP_K,
) -> list[RetrievedChunk]:
    """Embed `query` and return the top_k nearest chunks (cosine distance) for repo_id."""
    query_embedding = (await embedder.embed_batch([query]))[0]
    distance = chunks.c.embedding.cosine_distance(query_embedding).label("distance")

    stmt = (
        select(
            chunks.c.id,
            files.c.path,
            chunks.c.symbol_path,
            chunks.c.kind,
            chunks.c.start_line,
            chunks.c.end_line,
            chunks.c.content,
            chunks.c.token_count,
            distance,
        )
        .join(files, chunks.c.file_id == files.c.id)
        .where(files.c.repo_id == repo_id)
        .order_by(distance)
        .limit(top_k)
    )
    result = await session.execute(stmt)
    return [
        RetrievedChunk(
            chunk_id=row.id,
            file_path=row.path,
            symbol_path=row.symbol_path,
            kind=row.kind,
            start_line=row.start_line,
            end_line=row.end_line,
            content=row.content,
            token_count=row.token_count,
            distance=row.distance,
        )
        for row in result
    ]


async def search_chunks_bm25(
    session: AsyncSession,
    repo_id: uuid.UUID,
    query: str,
    top_k: int = DEFAULT_TOP_K,
) -> list[RetrievedChunk]:
    """Postgres full-text search ranking. Computed inline (no stored tsvector column
    or GIN index) — fine at this dataset size; would add an index before scaling up.
    `distance` is populated as 1 - rank purely so the field stays populated on a
    lower-is-better scale like `search_chunks`; RRF fusion uses rank position, not
    this value, so the two searches' scores never need to be directly comparable."""
    tsquery = func.plainto_tsquery("english", query)
    tsvector = func.to_tsvector("english", chunks.c.content)
    rank = func.ts_rank_cd(tsvector, tsquery).label("rank")

    stmt = (
        select(
            chunks.c.id,
            files.c.path,
            chunks.c.symbol_path,
            chunks.c.kind,
            chunks.c.start_line,
            chunks.c.end_line,
            chunks.c.content,
            chunks.c.token_count,
            rank,
        )
        .join(files, chunks.c.file_id == files.c.id)
        .where(files.c.repo_id == repo_id, tsvector.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(top_k)
    )
    result = await session.execute(stmt)
    return [
        RetrievedChunk(
            chunk_id=row.id,
            file_path=row.path,
            symbol_path=row.symbol_path,
            kind=row.kind,
            start_line=row.start_line,
            end_line=row.end_line,
            content=row.content,
            token_count=row.token_count,
            distance=1.0 - min(float(row.rank), 1.0),
        )
        for row in result
    ]


async def search_chunks_hybrid(
    session: AsyncSession,
    embedder: Embedder,
    repo_id: uuid.UUID,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    candidate_k: int = 20,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion of vector search and BM25 full-text search rankings:
    score = sum over rankers of 1 / (RRF_K + rank). Fuses on rank position, so the
    two rankers' raw scores never need to share a scale."""
    vector_results = await search_chunks(session, embedder, repo_id, query, top_k=candidate_k)
    bm25_results = await search_chunks_bm25(session, repo_id, query, top_k=candidate_k)

    fused_scores: dict[uuid.UUID, float] = {}
    chunk_by_id: dict[uuid.UUID, RetrievedChunk] = {}

    for rank, chunk in enumerate(vector_results, start=1):
        fused_scores[chunk.chunk_id] = fused_scores.get(chunk.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        chunk_by_id[chunk.chunk_id] = chunk

    for rank, chunk in enumerate(bm25_results, start=1):
        fused_scores[chunk.chunk_id] = fused_scores.get(chunk.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        chunk_by_id.setdefault(chunk.chunk_id, chunk)

    ranked_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)
    return [chunk_by_id[cid] for cid in ranked_ids[:top_k]]
