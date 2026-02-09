from __future__ import annotations
import queue
import threading
import time
import uuid
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.db import SessionLocal
from app.chunking import chunk_text
from app.providers.embeddings import embed
from app.observability import INGEST_JOBS, INGEST_LATENCY, timer

_jobs: "queue.Queue[uuid.UUID]" = queue.Queue()
_started = False

def enqueue(document_id: uuid.UUID) -> None:
    _jobs.put(document_id)

def start_worker() -> None:
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_loop, daemon=True)
    t.start()

def _loop() -> None:
    while True:
        doc_id = _jobs.get()
        try:
            process_document(doc_id)
        except Exception as e:
            print(f"[worker] fatal error processing {doc_id}: {e}")
        finally:
            _jobs.task_done()

def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

def process_document(document_id: uuid.UUID) -> None:
    run_id = uuid.uuid4()
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO ingestion_run (id, document_id, status) VALUES (:id, :doc, 'running')"),
            {"id": str(run_id), "doc": str(document_id)},
        )
        db.commit()

    with timer(INGEST_LATENCY):
        try:
            with SessionLocal() as db:
                doc = db.execute(
                    text("SELECT id::text, text FROM document WHERE id=:id"),
                    {"id": str(document_id)},
                ).mappings().first()
                if not doc:
                    raise ValueError("document not found")

                chunks = chunk_text(doc["text"])

                for idx, ch in enumerate(chunks):
                    v = embed(ch)
                    vlit = _vec_literal(v)

                    db.execute(
                        text("""
                          INSERT INTO document_chunk (id, document_id, chunk_index, chunk_text, embedding)
                          VALUES (:id, :document_id, :chunk_index, :chunk_text, :embedding::vector)
                          ON CONFLICT (document_id, chunk_index) DO NOTHING
                        """),
                        {
                            "id": str(uuid.uuid4()),
                            "document_id": str(document_id),
                            "chunk_index": idx,
                            "chunk_text": ch,
                            "embedding": vlit,
                        },
                    )

                db.execute(
                    text("UPDATE ingestion_run SET status='success', finished_at=now() WHERE id=:id"),
                    {"id": str(run_id)},
                )
                db.commit()

            INGEST_JOBS.labels(status="success").inc()

        except Exception as e:
            with SessionLocal() as db:
                db.execute(
                    text("UPDATE ingestion_run SET status='failed', error=:err, finished_at=now() WHERE id=:id"),
                    {"id": str(run_id), "err": str(e)},
                )
                db.commit()
            INGEST_JOBS.labels(status="failed").inc()
            raise
