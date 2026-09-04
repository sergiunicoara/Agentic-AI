"""Regression tests for app.indexing.index_state's cache-invalidation contract.

bump_index_epoch() is the mechanism that invalidates stale retrieval-cache
entries after ingestion (see app/ingestion/pipeline.py and
app/retrieval/pipeline.py's index_epoch-scoped cache key). If it stops
actually clearing the in-process WorkspaceIndexState cache — or stops
incrementing the DB row — retrieval silently goes back to serving
pre-ingestion results indefinitely, which is exactly the bug this session
fixed. These tests pin both halves of that contract.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

import app.indexing.index_state as index_state


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def first(self):
        return self._row

    def mappings(self):
        return self


class _FakeDB:
    def __init__(self, *, table_exists=True, state_row=None):
        self.table_exists = table_exists
        self.state_row = state_row
        self.executed: list[str] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append(sql)
        if "information_schema.tables" in sql:
            return _FakeResult((1,) if self.table_exists else None)
        if "FROM workspace_index_state" in sql and "SELECT" in sql:
            return _FakeResult(self.state_row)
        return _FakeResult(None)


def _fake_scope(db: _FakeDB):
    @contextmanager
    def _scope(*args, **kwargs):
        yield db

    return _scope


def _reset_module_cache():
    index_state._state_cache.clear()
    index_state._state_cache_expiry.clear()


class TestBumpIndexEpochClearsCache:

    def setup_method(self):
        _reset_module_cache()

    def teardown_method(self):
        _reset_module_cache()

    def test_bump_clears_state_cache_and_expiry(self, monkeypatch):
        index_state._state_cache["ws1"] = index_state.WorkspaceIndexState(
            workspace_id="ws1",
            active_embedding_version="v1",
            target_embedding_version=None,
            index_epoch=0,
            updated_at_s=time.time(),
        )
        index_state._state_cache_expiry["ws1"] = time.time() + 100

        db = _FakeDB()
        monkeypatch.setattr(index_state, "write_session_scope", _fake_scope(db))

        index_state.bump_index_epoch("ws1")

        assert "ws1" not in index_state._state_cache
        assert "ws1" not in index_state._state_cache_expiry

    def test_bump_issues_an_increment_write(self, monkeypatch):
        db = _FakeDB()
        monkeypatch.setattr(index_state, "write_session_scope", _fake_scope(db))

        index_state.bump_index_epoch("ws1")

        assert any("index_epoch" in sql and ("+ 1" in sql or "+1" in sql) for sql in db.executed)


class TestGetIndexStateReflectsBumpedEpochAfterCacheClear:

    def setup_method(self):
        _reset_module_cache()

    def teardown_method(self):
        _reset_module_cache()

    def test_stale_epoch_not_served_after_bump(self, monkeypatch):
        read_db = _FakeDB(
            table_exists=True,
            state_row={
                "workspace_id": "ws2",
                "active_embedding_version": "v1",
                "target_embedding_version": None,
                "index_epoch": 5,
                "updated_at_s": time.time(),
            },
        )
        monkeypatch.setattr(index_state, "read_session_scope", _fake_scope(read_db))

        st = index_state.get_index_state("ws2", ttl_s=100)
        assert st.index_epoch == 5

        # Second call within the TTL window must be served from the
        # in-process cache — no second DB round trip.
        calls_before = len(read_db.executed)
        st_cached = index_state.get_index_state("ws2", ttl_s=100)
        assert st_cached.index_epoch == 5
        assert len(read_db.executed) == calls_before

        # Ingestion happens: bump_index_epoch invalidates the cache.
        write_db = _FakeDB()
        monkeypatch.setattr(index_state, "write_session_scope", _fake_scope(write_db))
        index_state.bump_index_epoch("ws2")

        # Simulate the DB row now reflecting the bump.
        read_db.state_row = dict(read_db.state_row, index_epoch=6)

        # The very next read must NOT serve the stale epoch=5 from cache —
        # this is the exact bug class that was fixed this session.
        st_after = index_state.get_index_state("ws2", ttl_s=100)
        assert st_after.index_epoch == 6
