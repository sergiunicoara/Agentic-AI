"""Regression test: mark_success/mark_failure must not let a worker whose
lease already expired clobber the current owner's result.

claim_next() reclaims a job whose lease expired and hands it to a new
worker, bumping `attempts`. If the original (stale) worker eventually
finishes — late — and calls mark_success/mark_failure unconditionally by
job id, it overwrites whatever the new owner has since done, including a
genuine success already recorded. Both functions now match on `attempts`
as a fencing token: a write from a worker whose observed attempts no
longer matches the row's current attempts (because someone else has since
reclaimed it) becomes a no-op instead of a stale overwrite. This is tested
against a real lease-expiry race in the real-Postgres verification for
this fix; this test pins the SQL predicate shape with a fake DB.
"""
from __future__ import annotations

from app.ingestion.jobs import IngestionJob, mark_failure, mark_success


class _FakeResult:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _FakeDB:
    def __init__(self, *, matched: bool):
        self.matched = matched
        self.executed: list[tuple[str, dict]] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append((sql, params))
        return _FakeResult(rowcount=1 if self.matched else 0)


def _job(attempts: int) -> IngestionJob:
    return IngestionJob(
        id="11111111-1111-1111-1111-111111111111",
        job_type="document",
        workspace_id="demo",
        document_id="22222222-2222-2222-2222-222222222222",
        payload={},
        attempts=attempts,
        media=[],
    )


def test_mark_success_filters_by_attempts(monkeypatch):
    fake_db = _FakeDB(matched=True)
    import app.ingestion.jobs as jobs_module
    from contextlib import contextmanager

    @contextmanager
    def _scope():
        yield fake_db

    monkeypatch.setattr(jobs_module, "write_session_scope", _scope)

    mark_success(_job(attempts=3))

    sql, params = fake_db.executed[0]
    assert "attempts = :attempts" in sql
    assert params["attempts"] == 3


def test_mark_success_stale_write_is_a_noop_and_reported(monkeypatch):
    fake_db = _FakeDB(matched=False)  # simulates 0 rows matched (attempts moved on)
    import app.ingestion.jobs as jobs_module
    from contextlib import contextmanager

    @contextmanager
    def _scope():
        yield fake_db

    monkeypatch.setattr(jobs_module, "write_session_scope", _scope)

    captured = []
    monkeypatch.setattr(jobs_module, "emit_event", lambda name, payload: captured.append((name, payload)))

    mark_success(_job(attempts=1))

    assert captured and captured[0][0] == "ingestion_job_stale_completion"
    assert captured[0][1]["outcome"] == "success"


def test_mark_failure_filters_by_attempts(monkeypatch):
    fake_db = _FakeDB(matched=True)
    import app.ingestion.jobs as jobs_module
    from contextlib import contextmanager

    @contextmanager
    def _scope():
        yield fake_db

    monkeypatch.setattr(jobs_module, "write_session_scope", _scope)

    mark_failure(_job(attempts=2), RuntimeError("boom"))

    sql, params = fake_db.executed[0]
    assert "attempts = :attempts" in sql
    assert params["attempts"] == 2
