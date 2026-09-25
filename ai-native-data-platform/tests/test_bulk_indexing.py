"""Regression test for app.indexing.pipeline's bulk-indexing OpenSearch
dual-write correctness.

run_manifest()'s chunk-insert flush pre-generates a chunk id for every
candidate row, then does a single multi-row `INSERT ... ON CONFLICT DO
NOTHING RETURNING`. Only rows Postgres actually inserted come back — a row
that conflicts (already exists) keeps its ORIGINAL id, which is not the one
pre-generated for this call. Dual-writing the pre-generated id anyway would
push a document_chunk.id into OpenSearch that no Postgres row has, silently
breaking anything that joins back to document_chunk by id (the MMR
reranker's embedding lookup, in particular). This test drives run_manifest
against a fake DB that simulates a partial conflict and asserts the
OpenSearch payload only contains the row that was genuinely inserted, using
the id Postgres actually assigned.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import app.indexing.pipeline as pipeline


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, *, doc_rows, insert_returning_rows):
        self.doc_rows = doc_rows
        self.insert_returning_rows = insert_returning_rows
        self.insert_calls: list[dict] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "SET LOCAL statement_timeout" in sql:
            return _FakeResult()
        if "FROM document" in sql and "SELECT" in sql and "document_chunk" not in sql:
            return _FakeResult(self.doc_rows)
        if "INSERT INTO document_chunk" in sql:
            self.insert_calls.append(params)
            return _FakeResult(self.insert_returning_rows)
        raise AssertionError(f"unexpected SQL in fake DB: {sql}")


def _fake_scope(db: _FakeDB):
    @contextmanager
    def _scope(*args, **kwargs):
        yield db

    return _scope


def test_dual_write_uses_real_postgres_id_and_skips_conflicted_rows(monkeypatch, tmp_path):
    doc_id = "11111111-1111-1111-1111-111111111111"
    fake_db = _FakeDB(
        doc_rows=[{"id": doc_id, "text": "hello world. " * 20, "source_name": "upload"}],
        # Simulate Postgres reporting nothing inserted (conflict: this exact
        # chunk already existed under a different id) — the pre-generated
        # uuid4 for this call must NOT reach OpenSearch.
        insert_returning_rows=[],
    )
    monkeypatch.setattr(pipeline, "workspace_session_scope", _fake_scope(fake_db))
    monkeypatch.setattr(pipeline, "embed_batch", lambda texts: [[0.1, 0.2, 0.3] for _ in texts])

    captured: list[list[dict]] = []
    monkeypatch.setattr(pipeline, "_opensearch_dual_write_batch", lambda rows: captured.append(list(rows)))

    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"document_id": doc_id}) + "\n", encoding="utf-8")

    pipeline.run_manifest(str(manifest), workspace_id="demo", embedding_version="v1")

    sent = [row for batch in captured for row in batch]
    assert sent == [], (
        "a conflicted row (nothing returned by INSERT ... RETURNING) must not be "
        "dual-written using its pre-generated, non-existent id"
    )


def test_dual_write_uses_the_id_postgres_actually_assigned(monkeypatch, tmp_path):
    doc_id = "22222222-2222-2222-2222-222222222222"
    real_id = "99999999-9999-9999-9999-999999999999"
    fake_db = _FakeDB(
        doc_rows=[{"id": doc_id, "text": "hello world. " * 20, "source_name": "upload"}],
        # Postgres reports the row WAS freshly inserted, with this id — not
        # necessarily the uuid4 run_manifest pre-generated for the call.
        insert_returning_rows=[{"id": real_id, "document_id": doc_id, "chunk_index": 0}],
    )
    monkeypatch.setattr(pipeline, "workspace_session_scope", _fake_scope(fake_db))
    monkeypatch.setattr(pipeline, "embed_batch", lambda texts: [[0.1, 0.2, 0.3] for _ in texts])

    captured: list[list[dict]] = []
    monkeypatch.setattr(pipeline, "_opensearch_dual_write_batch", lambda rows: captured.append(list(rows)))

    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"document_id": doc_id}) + "\n", encoding="utf-8")

    pipeline.run_manifest(str(manifest), workspace_id="demo", embedding_version="v1")

    sent = [row for batch in captured for row in batch]
    assert len(sent) == 1
    assert sent[0]["chunk_id"] == real_id
    assert sent[0]["document_id"] == doc_id
