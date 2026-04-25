"""Tests for reliability contracts, SLO rolling window, and rate limiter."""
from __future__ import annotations

import time

import pytest

from app.core.reliability.contracts import (
    ReliabilityContract,
    ReliabilityViolation,
    enforce_groundedness,
    enforce_latency,
    enforce_non_empty,
)
from app.core.reliability.slo_window import RollingWindowSLO
from app.core.rate_limit import TokenBucket, WorkspaceRateLimiter


# ---------------------------------------------------------------------------
# Reliability contracts
# ---------------------------------------------------------------------------

CONTRACT = ReliabilityContract(
    max_request_latency_ms=800,
    max_empty_retrieval_rate=0.05,
    min_groundedness_mean=0.70,
)


class TestEnforceLatency:

    def test_within_ceiling_does_not_raise(self):
        enforce_latency(799, CONTRACT)  # no exception

    def test_exactly_at_ceiling_does_not_raise(self):
        enforce_latency(800, CONTRACT)

    def test_above_ceiling_raises(self):
        with pytest.raises(ReliabilityViolation):
            enforce_latency(801, CONTRACT)

    def test_high_latency_raises(self):
        with pytest.raises(ReliabilityViolation):
            enforce_latency(5000, CONTRACT)


class TestEnforceNonEmpty:

    def test_positive_count_does_not_raise(self):
        enforce_non_empty(1, CONTRACT)
        enforce_non_empty(10, CONTRACT)

    def test_zero_count_raises(self):
        with pytest.raises(ReliabilityViolation):
            enforce_non_empty(0, CONTRACT)

    def test_negative_count_raises(self):
        with pytest.raises(ReliabilityViolation):
            enforce_non_empty(-1, CONTRACT)


class TestEnforceGroundedness:

    def test_above_threshold_does_not_raise(self):
        enforce_groundedness(1.0, CONTRACT)
        enforce_groundedness(0.70, CONTRACT)

    def test_below_threshold_raises(self):
        with pytest.raises(ReliabilityViolation):
            enforce_groundedness(0.0, CONTRACT)

    def test_just_below_threshold_raises(self):
        with pytest.raises(ReliabilityViolation):
            enforce_groundedness(0.699, CONTRACT)


# ---------------------------------------------------------------------------
# Rolling SLO window
# ---------------------------------------------------------------------------

class TestRollingWindowSLO:

    def _make(self, max_events: int = 100) -> RollingWindowSLO:
        return RollingWindowSLO(max_events=max_events)

    def test_initial_snapshot_is_zero(self):
        slo = self._make()
        snap = slo.snapshot()
        assert snap["p95_latency_ms"] == 0.0
        assert snap["error_rate"] == 0.0
        assert snap["unknown_rate"] == 0.0

    def test_p95_single_value(self):
        slo = self._make()
        slo.observe(300.0, is_error=False, is_unknown=False)
        assert slo.snapshot()["p95_latency_ms"] == pytest.approx(300.0)

    def test_error_rate(self):
        slo = self._make()
        for _ in range(8):
            slo.observe(100.0, is_error=False, is_unknown=False)
        for _ in range(2):
            slo.observe(100.0, is_error=True, is_unknown=False)
        assert slo.snapshot()["error_rate"] == pytest.approx(0.2)

    def test_unknown_rate(self):
        slo = self._make()
        for _ in range(7):
            slo.observe(100.0, is_error=False, is_unknown=False)
        for _ in range(3):
            slo.observe(100.0, is_error=False, is_unknown=True)
        assert slo.snapshot()["unknown_rate"] == pytest.approx(0.3)

    def test_p95_ordering(self):
        slo = self._make()
        for v in range(1, 101):          # 1..100
            slo.observe(float(v), is_error=False, is_unknown=False)
        # p95 of 1..100 should be ≈ 95
        assert slo.snapshot()["p95_latency_ms"] == pytest.approx(95.0, abs=2.0)

    def test_window_evicts_old_events(self):
        slo = self._make(max_events=5)
        for _ in range(5):
            slo.observe(1000.0, is_error=True, is_unknown=False)
        # Now fill with good events — old ones evicted
        for _ in range(5):
            slo.observe(50.0, is_error=False, is_unknown=False)
        snap = slo.snapshot()
        assert snap["error_rate"] == pytest.approx(0.0)
        assert snap["p95_latency_ms"] < 100.0

    def test_all_errors(self):
        slo = self._make()
        for _ in range(10):
            slo.observe(200.0, is_error=True, is_unknown=False)
        assert slo.snapshot()["error_rate"] == pytest.approx(1.0)

    def test_zero_error_rate_when_no_errors(self):
        slo = self._make()
        for _ in range(10):
            slo.observe(100.0, is_error=False, is_unknown=False)
        assert slo.snapshot()["error_rate"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Rate limiter (token bucket)
# ---------------------------------------------------------------------------

class TestTokenBucket:

    def _bucket(self, rate: float = 10.0, capacity: int = 3) -> TokenBucket:
        return TokenBucket(rate=rate, capacity=capacity, tokens=float(capacity), last_refill=time.time())

    def test_allows_up_to_capacity(self):
        b = self._bucket(capacity=3)
        assert b.allow() is True
        assert b.allow() is True
        assert b.allow() is True

    def test_blocks_when_exhausted(self):
        b = self._bucket(capacity=2)
        b.allow()
        b.allow()
        assert b.allow() is False

    def test_refill_over_time(self):
        # Start with 0 tokens, set last_refill 1 second in the past
        b = TokenBucket(rate=5.0, capacity=10, tokens=0.0, last_refill=time.time() - 1.0)
        # After 1 second at rate=5, should have ≈5 tokens
        assert b.allow() is True

    def test_capacity_not_exceeded_on_refill(self):
        b = TokenBucket(rate=100.0, capacity=3, tokens=0.0, last_refill=time.time() - 10.0)
        # 10 seconds * 100 rps would be 1000, but capped at capacity=3
        assert b.allow() is True
        assert b.allow() is True
        assert b.allow() is True
        assert b.allow() is False  # capped at 3


class TestWorkspaceRateLimiter:

    def _limiter(self, monkeypatch) -> WorkspaceRateLimiter:
        monkeypatch.setattr("app.core.rate_limit.settings", type("S", (), {
            "per_workspace_rps": 10.0,
            "per_workspace_burst": 3,
        })())
        return WorkspaceRateLimiter()

    def test_new_workspace_gets_full_burst(self, monkeypatch):
        rl = self._limiter(monkeypatch)
        assert rl.allow("ws-a") is True
        assert rl.allow("ws-a") is True
        assert rl.allow("ws-a") is True

    def test_workspace_blocked_after_burst(self, monkeypatch):
        rl = self._limiter(monkeypatch)
        rl.allow("ws-b")
        rl.allow("ws-b")
        rl.allow("ws-b")
        assert rl.allow("ws-b") is False

    def test_different_workspaces_independent(self, monkeypatch):
        rl = self._limiter(monkeypatch)
        rl.allow("ws-x")
        rl.allow("ws-x")
        rl.allow("ws-x")
        # ws-x exhausted but ws-y should still be fresh
        assert rl.allow("ws-y") is True


# ---------------------------------------------------------------------------
# Groundedness utilities
# ---------------------------------------------------------------------------

class TestGroundedness:

    def test_valid_snippet_passes(self):
        from app.generation.groundedness import verify_citation_snippets
        contexts = [{"id": "c1", "text": "The refund policy allows 30 days."}]
        citations = [{"chunk_id": "c1", "snippet": "refund policy allows 30 days"}]
        ok, reason = verify_citation_snippets(contexts, citations)
        assert ok is True
        assert reason == "ok"

    def test_snippet_not_in_chunk_fails(self):
        from app.generation.groundedness import verify_citation_snippets
        contexts = [{"id": "c1", "text": "The refund policy allows 30 days."}]
        citations = [{"chunk_id": "c1", "snippet": "this text is not in the chunk"}]
        ok, reason = verify_citation_snippets(contexts, citations)
        assert ok is False

    def test_unknown_chunk_id_fails(self):
        from app.generation.groundedness import verify_citation_snippets
        contexts = [{"id": "c1", "text": "Some text."}]
        citations = [{"chunk_id": "c99", "snippet": "Some text"}]
        ok, reason = verify_citation_snippets(contexts, citations)
        assert ok is False
        assert "not_in_contexts" in reason

    def test_empty_snippet_fails(self):
        from app.generation.groundedness import verify_citation_snippets
        contexts = [{"id": "c1", "text": "Some text."}]
        citations = [{"chunk_id": "c1", "snippet": ""}]
        ok, reason = verify_citation_snippets(contexts, citations)
        assert ok is False

    def test_no_citations_passes(self):
        from app.generation.groundedness import verify_citation_snippets
        ok, reason = verify_citation_snippets([], [])
        assert ok is True

    def test_evidence_minimum_passes(self):
        from app.generation.groundedness import evidence_minimum
        citations = [{"snippet": "x" * 80}]
        ok, _ = evidence_minimum(citations, min_chars=80)
        assert ok is True

    def test_evidence_minimum_fails_when_too_short(self):
        from app.generation.groundedness import evidence_minimum
        citations = [{"snippet": "short"}]
        ok, reason = evidence_minimum(citations, min_chars=80)
        assert ok is False
        assert reason == "insufficient_evidence"

    def test_evidence_minimum_sums_across_citations(self):
        from app.generation.groundedness import evidence_minimum
        citations = [{"snippet": "x" * 40}, {"snippet": "y" * 40}]
        ok, _ = evidence_minimum(citations, min_chars=80)
        assert ok is True
