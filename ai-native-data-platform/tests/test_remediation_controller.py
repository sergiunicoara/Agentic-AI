"""Regression tests for the remediation controller's hysteresis logic.

evaluate_tick() is the pure decision core extracted from the controller's
background loop (app/core/reliability/remediation_controller.py) so it can
be exercised without threads, sleeps, or a real Postgres advisory lock.

Covers:
- the hysteresis walkthrough from the audit (a single good sample only
  decrements, it doesn't reset the streak)
- the trip threshold (3 consecutive violations)
- auto-clear on recovery — the fix for the "override applied but never
  reversed" gap the audit found (clear_override() previously had no caller
  anywhere in the app)
"""
from __future__ import annotations

from app.core.reliability.remediation_controller import evaluate_tick

THRESHOLDS = dict(
    min_samples=200,
    error_rate_threshold=0.25,
    unknown_rate_threshold=0.35,
    max_request_latency_ms=1000.0,
)

HEALTHY_SNAP = {"samples": 500, "error_rate": 0.0, "unknown_rate": 0.0, "p95_latency_ms": 100.0}
BAD_SNAP = {"samples": 500, "error_rate": 0.9, "unknown_rate": 0.0, "p95_latency_ms": 100.0}


class TestSampleGate:

    def test_below_min_samples_waits_and_does_not_change_violated(self):
        snap = {"samples": 50, "error_rate": 0.9, "unknown_rate": 0.0, "p95_latency_ms": 100.0}
        d = evaluate_tick(snap, violated=0, override_applied=False, **THRESHOLDS)
        assert d.action == "wait_for_samples"
        assert d.violated == 0


class TestHysteresis:

    def test_three_consecutive_violations_trips(self):
        violated = 0
        override_applied = False
        for _ in range(3):
            d = evaluate_tick(BAD_SNAP, violated=violated, override_applied=override_applied, **THRESHOLDS)
            violated, override_applied = d.violated, d.override_applied
        assert d.action == "applied"
        assert d.violated == 3
        assert d.override_applied is True

    def test_two_violations_one_good_one_violation_does_not_trip(self):
        # From the audit: v=1(bad) -> v=2(bad) -> v=1(good, decremented not
        # reset) -> v=2(bad). Counter never reaches 3.
        violated = 0
        override_applied = False
        sequence = [BAD_SNAP, BAD_SNAP, HEALTHY_SNAP, BAD_SNAP]
        for snap in sequence:
            d = evaluate_tick(snap, violated=violated, override_applied=override_applied, **THRESHOLDS)
            violated, override_applied = d.violated, d.override_applied
        assert violated == 2
        assert d.action == "none"
        assert override_applied is False

    def test_a_single_good_sample_only_decrements_not_resets(self):
        d = evaluate_tick(HEALTHY_SNAP, violated=2, override_applied=False, **THRESHOLDS)
        assert d.violated == 1  # not 0 — decrement, not reset
        assert d.action == "none"


class TestAutoClearOnRecovery:

    def test_recovery_to_zero_clears_an_applied_override(self):
        d = evaluate_tick(HEALTHY_SNAP, violated=1, override_applied=True, **THRESHOLDS)
        assert d.violated == 0
        assert d.action == "cleared"
        assert d.override_applied is False

    def test_recovery_when_no_override_was_applied_is_a_noop(self):
        d = evaluate_tick(HEALTHY_SNAP, violated=1, override_applied=False, **THRESHOLDS)
        assert d.violated == 0
        assert d.action == "none"
        assert d.override_applied is False

    def test_full_cycle_trip_then_recover_then_clear(self):
        violated = 0
        override_applied = False
        actions = []
        # Three violations trip it.
        for _ in range(3):
            d = evaluate_tick(BAD_SNAP, violated=violated, override_applied=override_applied, **THRESHOLDS)
            violated, override_applied = d.violated, d.override_applied
            actions.append(d.action)
        assert actions[-1] == "applied"
        assert override_applied is True

        # Three healthy samples bring the counter back to zero and clear it.
        for _ in range(3):
            d = evaluate_tick(HEALTHY_SNAP, violated=violated, override_applied=override_applied, **THRESHOLDS)
            violated, override_applied = d.violated, d.override_applied
            actions.append(d.action)

        assert actions[-1] == "cleared"
        assert violated == 0
        assert override_applied is False
