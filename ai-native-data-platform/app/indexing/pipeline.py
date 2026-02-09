from __future__ import annotations

import hashlib
import json
import os
import random
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from app.chunking import chunk_text
from app.core.config import settings
from app.core.observability import emit_event
from app.data.db import session_scope, write_session_scope
from app.providers.embeddings import embed_batch


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def _hash_text(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8", errors="ignore")).hexdigest()


@dataclass(frozen=True)
class IndexingConfig:
    """Config for large-corpus indexing.

    The online ingestion path (app/ingestion) is intentionally small and
    idempotent. This pipeline is for *bulk backfills* and *re-indexing* where
    throughput and checkpointing matter.
    """

    batch_size_docs: int = 250
    batch_size_chunks: int = 512
    embedding_batch_size: int = 96
    statement_timeout_ms: int = 30_000
    manifest_dir: str = "data/index_manifests"

    # Failure injection + retries (for soak/backfill hardening)
    fault_injection_rate: float = 0.0  # 0..1 probability of injected failure per doc
    max_retries: int = 3
    retry_backoff_ms: int = 250


def build_manifest(*, workspace_id: str, limit: int | None = None) -> Path:
    """Create a manifest file listing document ids to index.

    The manifest is append-only and can be used as an audit artifact.
    """
    manifest_dir = Path(IndexingConfig().manifest_dir)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    out = manifest_dir / f"manifest_{workspace_id}_{run_id}.jsonl"

    sql = "SELECT id::text AS id FROM document WHERE workspace_id=:ws ORDER BY created_at ASC"
    if limit is not None:
        sql += " LIMIT :lim"

    with session_scope() as db:
        rows = db.execute(text(sql), {"ws": workspace_id, "lim": int(limit or 0)}).mappings().all()

    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"document_id": r["id"]}) + "\n")

    return out


def run_manifest(
    manifest_path: str | os.PathLike,
    *,
    workspace_id: str,
    cfg: IndexingConfig | None = None,
    embedding_version: str | None = None,
) -> dict:
    """Run a bulk indexing job from a manifest.

    Checkpointing:
    - Each doc is processed independently.
    - Chunk inserts are idempotent via (document_id, chunk_index, embedding_version).

    Throughput:
    - Chunk texts are embedded in batches via embed_batch.
    - Inserts are executed in bulk.
    """
    cfg = cfg or IndexingConfig()
    embedding_version = embedding_version or settings.embedding_version
    path = Path(manifest_path)
    t0 = time.time()

    indexed_docs = 0
    indexed_chunks = 0
    skipped_docs = 0

    def _flush_chunk_batch(chunk_rows: list[dict]) -> int:
        if not chunk_rows:
            return 0

        # Failure injection to validate retry/idempotency behavior during backfills.
        # Simulates transient DB failures in a controlled way.
        if cfg.fault_injection_rate > 0.0 and random.random() < float(cfg.fault_injection_rate):
            raise RuntimeError("injected_flush_failure")

        attempt = 0
        while True:
            try:
                with write_session_scope() as db:
                    db.execute(text("SET LOCAL statement_timeout = :ms"), {"ms": int(cfg.statement_timeout_ms)})
                    db.execute(
                        text(
                            """
                            INSERT INTO document_chunk (
                              id, document_id, workspace_id, chunk_index, chunk_text, chunk_hash, embedding, embedding_version
                            )
                            VALUES (
                              :id, :document_id, :workspace_id, :chunk_index, :chunk_text, :chunk_hash, :embedding::vector, :embedding_version
                            )
                            ON CONFLICT (document_id, chunk_index, embedding_version) DO NOTHING
                            """
                        ),
                        chunk_rows,
                    )
                return len(chunk_rows)
            except Exception:
                attempt += 1
                if attempt > int(cfg.max_retries):
                    raise
                # Exponential backoff with jitter
                backoff_ms = min(int(cfg.max_backoff_ms), int((2 ** (attempt - 1)) * 100))
                time.sleep((backoff_ms / 1000.0) + random.random() * 0.05)


    with path.open("r", encoding="utf-8") as f:
        doc_ids: list[str] = []
        for line in f:
            if not line.strip():
                continue
            doc_ids.append(json.loads(line)["document_id"])

    # Process in doc batches to keep memory bounded.
    for i in range(0, len(doc_ids), cfg.batch_size_docs):
        batch = doc_ids[i : i + cfg.batch_size_docs]

        with session_scope() as db:
            db.execute(text("SET LOCAL statement_timeout = :ms"), {"ms": int(cfg.statement_timeout_ms)})
            rows = db.execute(
                text(
                    """
                    SELECT id::text AS id, text
                    FROM document
                    WHERE workspace_id=:ws AND id = ANY(:ids)
                    """
                ),
                {"ws": workspace_id, "ids": batch},
            ).mappings().all()

        docs = {r["id"]: (r.get("text") or "") for r in rows}

        # Produce chunk rows and embed in batches.
        pending_chunk_rows: list[dict] = []
        pending_chunk_texts: list[str] = []
        pending_chunk_meta: list[tuple[str, int, str]] = []  # (doc_id, idx, text)

        def _embed_and_stage() -> None:
            nonlocal pending_chunk_rows, pending_chunk_texts, pending_chunk_meta, indexed_chunks
            if not pending_chunk_texts:
                return
            vecs = embed_batch(pending_chunk_texts)
            for (doc_id, chunk_idx, ch_text), vec in zip(pending_chunk_meta, vecs, strict=False):
                pending_chunk_rows.append(
                    {
                        "id": str(uuid.uuid4()),
                        "document_id": doc_id,
                        "workspace_id": workspace_id,
                        "chunk_index": int(chunk_idx),
                        "chunk_text": ch_text,
                        "chunk_hash": _hash_text(ch_text),
                        "embedding": _vec_literal(vec),
                        "embedding_version": embedding_version,
                    }
                )

            pending_chunk_texts = []
            pending_chunk_meta = []

            if len(pending_chunk_rows) >= cfg.batch_size_chunks:
                indexed_chunks += _flush_chunk_batch(pending_chunk_rows)
                pending_chunk_rows = []

        for doc_id in batch:
            text_body = docs.get(doc_id)
            if not text_body:
                skipped_docs += 1
                continue
            chunks = chunk_text(text_body)
            for cidx, ch in enumerate(chunks):
                pending_chunk_texts.append(ch)
                pending_chunk_meta.append((doc_id, cidx, ch))
                if len(pending_chunk_texts) >= cfg.embedding_batch_size:
                    _embed_and_stage()
            indexed_docs += 1

        # Flush tail
        _embed_and_stage()
        indexed_chunks += _flush_chunk_batch(pending_chunk_rows)

        emit_event(
            "bulk_index_progress",
            {
                "workspace_id": workspace_id,
                "docs_done": indexed_docs,
                "chunks_done": indexed_chunks,
                "docs_skipped": skipped_docs,
            },
        )

    return {
        "workspace_id": workspace_id,
        "manifest": str(path),
        "indexed_docs": indexed_docs,
        "indexed_chunks": indexed_chunks,
        "skipped_docs": skipped_docs,
        "embedding_version": embedding_version,
        "duration_s": round(time.time() - t0, 3),
    }
