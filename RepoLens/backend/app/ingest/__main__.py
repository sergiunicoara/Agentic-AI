import argparse
import asyncio
import json
import logging
import shutil
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_factory
from app.ingest import chunker, store, walker
from app.ingest.embedder import Embedder, FakeEmbedder, OpenAIEmbedder, context_header
from app.ingest.models import SourceFile
from app.observability import span

logger = logging.getLogger("ingest")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {"level": record.levelname, "logger": record.name}
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def _log(event: str, **fields: object) -> None:
    logger.info(event, extra={"extra_fields": {"event": event, **fields}})


async def _ingest_file(
    session: AsyncSession,
    repo_id,
    repo_label: str,
    source_file: SourceFile,
    embedder: Embedder,
) -> tuple[int, bool]:
    """Returns (chunk_count, was_skipped_unchanged)."""
    text = source_file.abs_path.read_bytes().decode("utf-8", errors="replace")
    content_hash = store.compute_content_hash(text)

    existing_hash = await store.existing_file_hash(session, repo_id, source_file.path)
    if existing_hash == content_hash:
        return 0, True

    chunk_records = chunker.chunk_file(source_file)
    embeddings: list[list[float]] = []
    if chunk_records:
        embed_inputs = [
            context_header(
                repo_label, source_file.path, c.symbol_path, c.docstring_first_line, c.content
            )
            for c in chunk_records
        ]
        embeddings = await embedder.embed_batch(embed_inputs)

    loc = text.count("\n") + 1
    count = await store.replace_file(
        session,
        repo_id,
        source_file.path,
        source_file.language,
        loc,
        content_hash,
        text,
        chunk_records,
        embeddings,
    )
    return count, False


async def run(source: str, use_fake_embeddings: bool, subdir: str | None = None) -> None:
    _configure_logging()
    started = time.monotonic()

    repo_path, is_temp_clone = walker.resolve_source(source)
    _log("resolved_source", source=source, path=str(repo_path), cloned=is_temp_clone, subdir=subdir)

    try:
        with span("ingest.run", source=source, subdir=subdir):
            files_found = walker.walk(repo_path, subdir=subdir)
            _log("walk_complete", file_count=len(files_found))

            embedder: Embedder = FakeEmbedder() if use_fake_embeddings else OpenAIEmbedder()

            async with session_factory()() as session:
                repo_id = await store.get_or_create_repo(session, source)
                removed = await store.delete_missing_files(
                    session, repo_id, {source_file.path for source_file in files_found}
                )
                if removed:
                    _log("stale_files_removed", count=removed)

                total_chunks = 0
                skipped = 0
                for i, source_file in enumerate(files_found, start=1):
                    count, was_skipped = await _ingest_file(
                        session, repo_id, source, source_file, embedder
                    )
                    total_chunks += count
                    skipped += int(was_skipped)
                    _log(
                        "file_ingested",
                        path=source_file.path,
                        chunk_count=count,
                        skipped=was_skipped,
                        progress=f"{i}/{len(files_found)}",
                    )

                await store.finalize_repo_counts(session, repo_id)
                await session.commit()

            elapsed = time.monotonic() - started
            _log(
                "ingest_complete",
                file_count=len(files_found),
                skipped_unchanged=skipped,
                chunk_count=total_chunks,
                elapsed_seconds=round(elapsed, 2),
            )
    finally:
        if is_temp_clone:
            shutil.rmtree(repo_path, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest a repo (URL or local path) into the codex index."
    )
    parser.add_argument("source", help="GitHub URL or local path to index")
    parser.add_argument(
        "--fake-embeddings",
        action="store_true",
        help="Use a deterministic offline embedder instead of the real OpenAI API (dry runs/tests)",
    )
    parser.add_argument(
        "--subdir",
        default=None,
        help="Scope ingestion to a subdirectory of the repo (e.g. a package dir), "
        "still resolving .gitignore from the repo root",
    )
    args = parser.parse_args()
    asyncio.run(run(args.source, args.fake_embeddings, args.subdir))


if __name__ == "__main__":
    main()
