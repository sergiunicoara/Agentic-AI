"""Unit tests for app/opensearch/reconcile.py.

All tests use mocks — no real OpenSearch or Postgres instance required.
Per the "patch the usage site, not the definition site" lesson (tasks/lessons.md),
everything reconcile.py imports with `from X import Y` is patched as
`app.opensearch.reconcile.Y`, not `X.Y`.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from app.indexing.index_state import WorkspaceIndexState


def _fake_ws_session_scope(batches: list[list[dict]]):
    """Returns a context-manager factory that hands back one batch of rows
    per `with` entry (one entry per reconcile_workspace() scan iteration),
    matching real workspace_session_scope's per-call semantics.
    """
    calls = {"n": 0}

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return self

        def all(self):
            return self._rows

    class _FakeDB:
        def execute(self, *_a, **_kw):
            rows = batches[calls["n"]] if calls["n"] < len(batches) else []
            calls["n"] += 1
            return _Result(rows)

    @contextmanager
    def scope(_workspace_id, *_a, **_kw):
        yield _FakeDB()

    return scope


def _row(chunk_id: str, document_id: str, chunk_index: int, text: str = "hi") -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "chunk_index": chunk_index,
        "chunk_text": text,
        "embedding": "[0.100000,0.200000]",
    }


class _FakeOSClient:
    def __init__(self, found_ids: set[str]):
        self.found_ids = found_ids
        self.mget_calls: list[list[str]] = []

    def mget(self, *, index, body):
        ids = body["ids"]
        self.mget_calls.append(ids)
        return {"docs": [{"_id": i, "found": i in self.found_ids} for i in ids]}


class TestReconcileWorkspaceSkips:
    def test_skipped_when_dual_write_disabled(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.opensearch_dual_write", False)
        monkeypatch.setattr("app.core.config.settings.opensearch_url", "http://localhost:9200")
        monkeypatch.setattr(
            "app.opensearch.reconcile.get_index_state",
            lambda ws: WorkspaceIndexState(ws, "v1", None, 0, 0.0),
        )

        from app.opensearch.reconcile import reconcile_workspace
        report = reconcile_workspace("ws1")

        assert report.skipped_reason == "opensearch_dual_write_disabled"
        assert report.checked == 0

    def test_skipped_when_opensearch_unavailable(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.opensearch_dual_write", True)
        monkeypatch.setattr("app.core.config.settings.opensearch_url", "http://localhost:9200")
        monkeypatch.setattr(
            "app.opensearch.reconcile.get_index_state",
            lambda ws: WorkspaceIndexState(ws, "v1", None, 0, 0.0),
        )
        monkeypatch.setattr("app.opensearch.reconcile.is_available", lambda: False)

        from app.opensearch.reconcile import reconcile_workspace
        report = reconcile_workspace("ws1")

        assert report.skipped_reason == "opensearch_unavailable"


class TestReconcileWorkspaceRepairs:
    def _enable(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.opensearch_dual_write", True)
        monkeypatch.setattr("app.core.config.settings.opensearch_url", "http://localhost:9200")
        monkeypatch.setattr("app.core.config.settings.opensearch_index", "ai_platform_chunks")
        monkeypatch.setattr(
            "app.opensearch.reconcile.get_index_state",
            lambda ws: WorkspaceIndexState(ws, "v1", None, 0, 0.0),
        )
        monkeypatch.setattr("app.opensearch.reconcile.is_available", lambda: True)
        monkeypatch.setattr("app.opensearch.reconcile.persist_trace", lambda **kw: None)

    def test_repairs_only_the_chunk_missing_from_opensearch(self, monkeypatch):
        self._enable(monkeypatch)

        rows = [_row("c1", "d1", 0), _row("c2", "d1", 1)]
        monkeypatch.setattr(
            "app.opensearch.reconcile.workspace_session_scope",
            _fake_ws_session_scope([rows]),
        )
        # c1's doc_key is present, c2's is missing.
        fake_client = _FakeOSClient(found_ids={"d1:0:v1"})
        monkeypatch.setattr("app.opensearch.client.get_client", lambda: fake_client)

        with patch(
            "app.opensearch.reconcile.bulk_upsert", return_value={"indexed": 1, "errors": 0}
        ) as mock_bulk:
            from app.opensearch.reconcile import reconcile_workspace
            report = reconcile_workspace("ws1")

        assert report.checked == 2
        assert report.missing == 1
        assert report.repaired == 1
        assert report.repair_failed == 0
        assert report.skipped_reason is None

        repaired_payload = mock_bulk.call_args[0][0]
        assert len(repaired_payload) == 1
        assert repaired_payload[0]["document_id"] == "d1"
        assert repaired_payload[0]["chunk_index"] == 1
        assert repaired_payload[0]["embedding"] == [0.1, 0.2]

    def test_no_repair_call_when_nothing_missing(self, monkeypatch):
        self._enable(monkeypatch)

        rows = [_row("c1", "d1", 0)]
        monkeypatch.setattr(
            "app.opensearch.reconcile.workspace_session_scope",
            _fake_ws_session_scope([rows]),
        )
        fake_client = _FakeOSClient(found_ids={"d1:0:v1"})
        monkeypatch.setattr("app.opensearch.client.get_client", lambda: fake_client)

        with patch("app.opensearch.reconcile.bulk_upsert") as mock_bulk:
            from app.opensearch.reconcile import reconcile_workspace
            report = reconcile_workspace("ws1")

        mock_bulk.assert_not_called()
        assert report.checked == 1
        assert report.missing == 0
        assert report.repaired == 0

    def test_scans_only_the_active_embedding_version(self, monkeypatch):
        """A chunk under a stale/target embedding_version must never be
        scanned — that divergence is expected, not a bug (see module
        docstring)."""
        self._enable(monkeypatch)
        monkeypatch.setattr(
            "app.opensearch.reconcile.get_index_state",
            lambda ws: WorkspaceIndexState(ws, "v2", "v3", 0, 0.0),
        )

        captured_params = {}

        @contextmanager
        def scope(_ws, *_a, **_kw):
            class _Result:
                def mappings(self):
                    return self

                def all(self):
                    return []

            class _FakeDB:
                def execute(self, _stmt, params):
                    captured_params.update(params)
                    return _Result()

            yield _FakeDB()

        monkeypatch.setattr("app.opensearch.reconcile.workspace_session_scope", scope)
        monkeypatch.setattr("app.opensearch.client.get_client", lambda: _FakeOSClient(found_ids=set()))

        from app.opensearch.reconcile import reconcile_workspace
        report = reconcile_workspace("ws1")

        assert captured_params["ev"] == "v2"
        assert report.embedding_version == "v2"

    def test_repair_failure_is_recorded_not_raised(self, monkeypatch):
        self._enable(monkeypatch)

        rows = [_row("c1", "d1", 0)]
        monkeypatch.setattr(
            "app.opensearch.reconcile.workspace_session_scope",
            _fake_ws_session_scope([rows]),
        )
        fake_client = _FakeOSClient(found_ids=set())
        monkeypatch.setattr("app.opensearch.client.get_client", lambda: fake_client)

        with patch("app.opensearch.reconcile.bulk_upsert", side_effect=Exception("timeout")):
            from app.opensearch.reconcile import reconcile_workspace
            report = reconcile_workspace("ws1")  # must not raise

        assert report.missing == 1
        assert report.repair_failed == 1
        assert report.repaired == 0

    def test_never_imports_or_calls_delete(self):
        """Reconciliation must stay one-directional: repair, never delete.
        delete_by_document is untested/uncalled dead code elsewhere in the
        repo (tasks/todo.md) — this job must not be the first caller."""
        import app.opensearch.reconcile as reconcile_mod

        assert not hasattr(reconcile_mod, "delete_by_document")
