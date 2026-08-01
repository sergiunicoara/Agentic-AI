from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import text

from app.core.config import settings
from app.data.db import write_session_scope


@dataclass(frozen=True)
class IngestionJob:
    id: str
    job_type: str
    workspace_id: str
    document_id: str | None
    payload: dict
    attempts: int
    media: list[tuple[bytes, str]]


_WORKER_ID = f"{os.getenv('HOSTNAME', 'worker')}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def enqueue_document(document_id: str, workspace_id: str) -> str:
    return _insert_job(
        job_type="document",
        workspace_id=workspace_id,
        document_id=document_id,
        payload={},
        media=[],
    )


def enqueue_images(
    workspace_id: str,
    source_name: str,
    images: list[tuple[bytes, str]],
    *,
    external_id: str | None = None,
    document_id: str | None = None,
) -> str:
    return _insert_job(
        job_type="image",
        workspace_id=workspace_id,
        document_id=document_id,
        payload={"source_name": source_name, "external_id": external_id},
        media=images,
    )


def _insert_job(*, job_type: str, workspace_id: str, document_id: str | None, payload: dict, media: list[tuple[bytes, str]]) -> str:
    job_id = str(uuid.uuid4())
    with write_session_scope() as db:
        db.execute(
            text(
                """
                INSERT INTO ingestion_job (id, job_type, workspace_id, document_id, payload, status)
                VALUES (:id, :job_type, :workspace_id, CAST(:document_id AS uuid), CAST(:payload AS jsonb), 'queued')
                """
            ),
            {
                "id": job_id,
                "job_type": job_type,
                "workspace_id": workspace_id,
                "document_id": document_id,
                "payload": json.dumps(payload),
            },
        )
        for ordinal, (content, mime_type) in enumerate(media):
            db.execute(
                text(
                    """
                    INSERT INTO ingestion_job_media (id, job_id, ordinal, mime_type, content)
                    VALUES (:id, :job_id, :ordinal, :mime_type, :content)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "job_id": job_id,
                    "ordinal": ordinal,
                    "mime_type": mime_type,
                    "content": content,
                },
            )
    return job_id


def claim_next() -> IngestionJob | None:
    """Atomically lease one due job.

    SKIP LOCKED lets multiple worker replicas make progress without polling the
    same job. Expired leases are retried after a worker restart or crash.
    """
    with write_session_scope() as db:
        # A worker can die while holding a lease. Once it has exhausted its
        # retry budget, make that terminal state visible instead of leasing it
        # forever on every subsequent worker restart.
        db.execute(
            text(
                """
                UPDATE ingestion_job
                SET status = 'failed',
                    locked_at = NULL,
                    locked_by = NULL,
                    last_error = COALESCE(last_error, 'worker lease expired'),
                    updated_at = now()
                WHERE status = 'running'
                  AND locked_at < now() - make_interval(secs => :lease_seconds)
                  AND attempts >= :max_attempts
                """
            ),
            {
                "lease_seconds": int(settings.ingestion_job_lease_s),
                "max_attempts": int(settings.ingestion_job_max_attempts),
            },
        )
        row = db.execute(
            text(
                """
                WITH candidate AS (
                  SELECT id
                  FROM ingestion_job
                  WHERE (status = 'queued' AND available_at <= now())
                     OR (status = 'running'
                         AND locked_at < now() - make_interval(secs => :lease_seconds)
                         AND attempts < :max_attempts)
                  ORDER BY available_at, created_at
                  FOR UPDATE SKIP LOCKED
                  LIMIT 1
                )
                UPDATE ingestion_job AS j
                SET status = 'running',
                    attempts = j.attempts + 1,
                    locked_at = now(),
                    locked_by = :worker_id,
                    updated_at = now()
                FROM candidate
                WHERE j.id = candidate.id
                RETURNING j.id::text, j.job_type, j.workspace_id, j.document_id::text,
                          j.payload, j.attempts
                """
            ),
            {
                "lease_seconds": int(settings.ingestion_job_lease_s),
                "max_attempts": int(settings.ingestion_job_max_attempts),
                "worker_id": _WORKER_ID,
            },
        ).mappings().first()
        if not row:
            return None
        media_rows = db.execute(
            text(
                """
                SELECT content, mime_type
                FROM ingestion_job_media
                WHERE job_id = CAST(:job_id AS uuid)
                ORDER BY ordinal
                """
            ),
            {"job_id": row["id"]},
        ).mappings().all()

    raw_payload = row["payload"]
    payload = json.loads(raw_payload) if isinstance(raw_payload, str) else dict(raw_payload or {})
    return IngestionJob(
        id=row["id"],
        job_type=row["job_type"],
        workspace_id=row["workspace_id"],
        document_id=row["document_id"],
        payload=payload,
        attempts=int(row["attempts"]),
        media=[(bytes(media["content"]), str(media["mime_type"])) for media in media_rows],
    )


def mark_success(job_id: str) -> None:
    with write_session_scope() as db:
        db.execute(
            text(
                """
                UPDATE ingestion_job
                SET status = 'succeeded', locked_at = NULL, locked_by = NULL, updated_at = now()
                WHERE id = CAST(:job_id AS uuid)
                """
            ),
            {"job_id": job_id},
        )


def mark_failure(job: IngestionJob, error: Exception) -> None:
    retry = job.attempts < int(settings.ingestion_job_max_attempts)
    delay_s = min(300, 2 ** max(0, job.attempts - 1))
    status = "queued" if retry else "failed"
    with write_session_scope() as db:
        db.execute(
            text(
                """
                UPDATE ingestion_job
                SET status = :status,
                    available_at = now() + make_interval(secs => :delay_s),
                    locked_at = NULL,
                    locked_by = NULL,
                    last_error = :error,
                    updated_at = now()
                WHERE id = CAST(:job_id AS uuid)
                """
            ),
            {"job_id": job.id, "status": status, "delay_s": delay_s, "error": str(error)[:4000]},
        )


def run_forever(handler: Callable[[IngestionJob], None]) -> None:
    while True:
        job = claim_next()
        if job is None:
            time.sleep(float(settings.ingestion_job_poll_s))
            continue
        try:
            handler(job)
        except Exception as exc:
            mark_failure(job, exc)
        else:
            mark_success(job.id)
