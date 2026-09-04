from __future__ import annotations

"""Leader-elected remediation controller.

The API can run with multiple replicas. Remediation should run once cluster-wide.
We elect a leader using a Postgres advisory lock and only the leader performs
the closed-loop mitigation.
"""

import threading
import time
from dataclasses import dataclass

from app.core.config import settings
from app.core.observability import emit_event
from app.core.reliability.leader import LeaderLock, release, try_acquire
from app.core.reliability.remediation import _write_override, clear_override, has_override
from app.core.reliability.slo_window import rolling_slo


DEFAULT_LOCK_KEY = 914_002_777  # stable constant for this demo repo


@dataclass(frozen=True)
class TickDecision:
    violated: int
    override_applied: bool
    action: str  # "none" | "wait_for_samples" | "applied" | "cleared"
    bad: bool | None = None


def evaluate_tick(
    snap: dict,
    *,
    violated: int,
    override_applied: bool,
    min_samples: int,
    error_rate_threshold: float,
    unknown_rate_threshold: float,
    max_request_latency_ms: float,
) -> TickDecision:
    """Pure hysteresis decision — no I/O, so it's directly unit-testable.

    Given the current rolling-SLO snapshot and controller state, decides
    whether to (a) wait for more samples, (b) do nothing this tick, (c) apply
    the remediation override, or (d) clear a previously-applied override now
    that the SLO has recovered. The caller (_loop below) is responsible for
    actually performing the DB writes this decision implies.
    """
    if int(snap.get("samples", 0)) < int(min_samples):
        return TickDecision(violated=violated, override_applied=override_applied, action="wait_for_samples")

    bad = (
        snap["error_rate"] >= float(error_rate_threshold)
        or snap["unknown_rate"] >= float(unknown_rate_threshold)
        or snap["p95_latency_ms"] >= float(max_request_latency_ms)
    )
    violated = violated + 1 if bad else max(0, violated - 1)

    if violated >= 3:
        return TickDecision(violated=violated, override_applied=True, action="applied", bad=bad)
    if violated == 0 and override_applied:
        # Fully recovered (hysteresis counter back to zero) after having
        # forced traffic to the safe experiment — reverse it automatically
        # instead of requiring a human to find and delete the override row.
        return TickDecision(violated=violated, override_applied=False, action="cleared", bad=bad)
    return TickDecision(violated=violated, override_applied=override_applied, action="none", bad=bad)


def start_controller(
    *,
    lock_key: int = DEFAULT_LOCK_KEY,
    error_rate_threshold: float = 0.25,
    unknown_rate_threshold: float = 0.35,
    max_request_latency_ms: float | None = None,
    min_samples: int = 200,
    check_every_s: float = 5.0,
    force_experiment: str | None = None,
    leader_renew_every_s: float = 3.0,
) -> None:
    """Start the leader-elected remediation controller."""

    force_experiment = force_experiment or settings.ab_default_experiment
    if max_request_latency_ms is None:
        max_request_latency_ms = float(settings.max_request_latency_ms) * 1.25

    lock = LeaderLock(key=int(lock_key))

    def _loop() -> None:
        is_leader = False
        violated = 0
        # Tracks whether *this* leader session believes an override is
        # currently applied, so it knows when to auto-clear it on recovery.
        # Seeded from the actual DB row on leader acquisition (not assumed
        # False) so a leadership handoff mid-remediation doesn't strand an
        # override that the new leader doesn't know exists.
        override_applied = False
        last_leader_check = 0.0

        while True:
            now = time.time()

            # Attempt to become leader periodically.
            if now - last_leader_check >= leader_renew_every_s:
                last_leader_check = now
                try:
                    acquired = try_acquire(lock)
                except Exception:
                    acquired = False

                if acquired and not is_leader:
                    is_leader = True
                    try:
                        override_applied = has_override()
                    except Exception:
                        override_applied = False
                    emit_event("remediation_leader_acquired", {"lock_key": lock_key, "override_already_applied": override_applied})
                elif not acquired and is_leader:
                    # Lost leadership — release our local handle so a stale
                    # connection object doesn't make a future try_acquire()
                    # short-circuit to "still leader" against a lock we no
                    # longer hold.
                    is_leader = False
                    violated = 0
                    try:
                        release(lock)
                    except Exception:
                        pass
                    emit_event("remediation_leader_lost", {"lock_key": lock_key})

            if not is_leader:
                time.sleep(check_every_s)
                continue

            try:
                snap = rolling_slo.snapshot()
                decision = evaluate_tick(
                    snap,
                    violated=violated,
                    override_applied=override_applied,
                    min_samples=min_samples,
                    error_rate_threshold=error_rate_threshold,
                    unknown_rate_threshold=unknown_rate_threshold,
                    max_request_latency_ms=max_request_latency_ms,
                )
                violated = decision.violated
                override_applied = decision.override_applied

                if decision.action == "wait_for_samples":
                    time.sleep(check_every_s)
                    continue
                elif decision.action == "applied":
                    _write_override(force_experiment)
                    emit_event(
                        "remediation_applied",
                        {
                            "force_experiment": force_experiment,
                            "snapshot": snap,
                            "thresholds": {
                                "error_rate": error_rate_threshold,
                                "unknown_rate": unknown_rate_threshold,
                                "p95_latency_ms": max_request_latency_ms,
                            },
                        },
                    )
                elif decision.action == "cleared":
                    clear_override()
                    emit_event("remediation_cleared", {"force_experiment": force_experiment, "snapshot": snap})

            except Exception as e:
                emit_event("remediation_error", {"error": str(e)})

            time.sleep(check_every_s)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
