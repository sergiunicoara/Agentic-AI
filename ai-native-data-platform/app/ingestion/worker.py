"""Compatibility exports for the durable ingestion worker.

The previous module implemented a second, process-local queue with stale
database imports. Keep this import path stable while routing all callers to
the durable worker implementation.
"""

from app.ingestion.pipeline import enqueue, process_document, start_worker

__all__ = ["enqueue", "process_document", "start_worker"]
