"""Regression test: online ingestion must tag new chunks with the
workspace's *active* embedding version, not the process-level
settings.embedding_version default.

After a reindex cutover (app.indexing.index_state.promote_target_to_active
/ set_active_embedding_version), a workspace's active_embedding_version can
differ from the env-level default every API/worker process was started
with. Tagging newly ingested chunks with the stale env default instead of
the workspace's real active version makes them invisible to retrieval
(which always reads chunks WHERE embedding_version = active_embedding_version)
without any error or signal.
"""
from __future__ import annotations

from contextlib import contextmanager

import app.ingestion.pipeline as pipeline


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _FakeDB:
    """Captures every INSERT's params so we can assert on embedding_version."""

    def __init__(self, *, doc_row):
        self.doc_row = doc_row
        self.chunk_insert_params: list[dict] = []
        self.run_insert_params: list[dict] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "INSERT INTO ingestion_run" in sql:
            self.run_insert_params.append(params)
            return _FakeResult()
        if "SELECT id::text, workspace_id, source_name, text FROM document" in sql:
            return _FakeResult(self.doc_row)
        if "INSERT INTO document_chunk" in sql:
            self.chunk_insert_params.append(params)
            # Simulate a fresh insert (RETURNING yields the row's id).
            return _FakeResult((params["id"],))
        if "UPDATE ingestion_run" in sql:
            return _FakeResult()
        raise AssertionError(f"unexpected SQL in fake DB: {sql}")


def _fake_scope(db: _FakeDB):
    @contextmanager
    def _scope(*args, **kwargs):
        yield db

    return _scope


def test_process_document_tags_chunks_with_workspace_active_version_not_env_default(monkeypatch):
    doc_id = "33333333-3333-3333-3333-333333333333"
    fake_db = _FakeDB(
        doc_row={
            "id": doc_id,
            "workspace_id": "demo",
            "source_name": "upload",
            "text": "some document text that is long enough to form a chunk",
        }
    )
    monkeypatch.setattr(pipeline, "workspace_session_scope", _fake_scope(fake_db))
    monkeypatch.setattr(pipeline, "embed_batch", lambda texts: [[0.1, 0.2] for _ in texts])
    monkeypatch.setattr(pipeline, "_opensearch_dual_write_batch", lambda rows: None)

    # settings.embedding_version (the stale env default) says "v1", but this
    # workspace's real active version (post-reindex-cutover) is "v2".
    monkeypatch.setattr(pipeline.settings, "embedding_version", "v1")

    class _FakeIndexState:
        active_embedding_version = "v2"

    monkeypatch.setattr(
        "app.indexing.index_state.get_index_state",
        lambda workspace_id: _FakeIndexState(),
    )

    pipeline.process_document(doc_id, "demo")

    assert fake_db.run_insert_params[0]["v"] == "v2"
    assert len(fake_db.chunk_insert_params) == 1
    assert fake_db.chunk_insert_params[0]["embedding_version"] == "v2"
