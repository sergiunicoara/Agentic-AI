import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.models import ChunkRecord
from app.tables import chunks, files, repos


def compute_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def get_or_create_repo(session: AsyncSession, source_url: str) -> uuid.UUID:
    result = await session.execute(select(repos.c.id).where(repos.c.source_url == source_url))
    row = result.first()
    if row:
        return row[0]
    repo_id = uuid.uuid4()
    await session.execute(insert(repos).values(id=repo_id, source_url=source_url))
    return repo_id


async def existing_file_hash(session: AsyncSession, repo_id: uuid.UUID, path: str) -> str | None:
    result = await session.execute(
        select(files.c.content_hash).where(files.c.repo_id == repo_id, files.c.path == path)
    )
    row = result.first()
    return row[0] if row else None


async def delete_missing_files(
    session: AsyncSession, repo_id: uuid.UUID, current_paths: set[str]
) -> int:
    """Remove files no longer present in the current source snapshot."""
    stmt = select(files.c.id, files.c.path).where(files.c.repo_id == repo_id)
    existing = list((await session.execute(stmt)).all())
    stale_ids = [row.id for row in existing if row.path not in current_paths]
    if stale_ids:
        await session.execute(delete(files).where(files.c.id.in_(stale_ids)))
    return len(stale_ids)


async def replace_file(
    session: AsyncSession,
    repo_id: uuid.UUID,
    path: str,
    language: str,
    loc: int,
    content_hash: str,
    content: str,
    chunk_records: list[ChunkRecord],
    embeddings: list[list[float]],
) -> int:
    """Delete any existing row for this (repo_id, path) and insert the fresh file + chunks."""
    await session.execute(delete(files).where(files.c.repo_id == repo_id, files.c.path == path))

    file_id = uuid.uuid4()
    await session.execute(
        insert(files).values(
            id=file_id,
            repo_id=repo_id,
            path=path,
            language=language,
            loc=loc,
            content_hash=content_hash,
            content=content,
        )
    )
    if chunk_records:
        await session.execute(
            insert(chunks),
            [
                {
                    "id": uuid.uuid4(),
                    "file_id": file_id,
                    "symbol_path": record.symbol_path,
                    "kind": record.kind.value,
                    "start_line": record.start_line,
                    "end_line": record.end_line,
                    "content": record.content,
                    "embedding": embedding,
                    "token_count": record.token_count,
                }
                for record, embedding in zip(chunk_records, embeddings, strict=True)
            ],
        )
    return len(chunk_records)


async def finalize_repo_counts(session: AsyncSession, repo_id: uuid.UUID) -> None:
    file_count = (
        await session.execute(
            select(func.count()).select_from(files).where(files.c.repo_id == repo_id)
        )
    ).scalar_one()
    chunk_count = (
        await session.execute(
            select(func.count())
            .select_from(chunks)
            .join(files, chunks.c.file_id == files.c.id)
            .where(files.c.repo_id == repo_id)
        )
    ).scalar_one()
    await session.execute(
        update(repos)
        .where(repos.c.id == repo_id)
        .values(file_count=file_count, chunk_count=chunk_count, indexed_at=datetime.now(UTC))
    )
