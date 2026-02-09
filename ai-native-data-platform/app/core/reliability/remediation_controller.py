from __future__ import annotations

"""Leader-elected remediation controller.

The API can run with multiple replicas. Remediation should run once cluster-wide.
We elect a leader using a Postgres advisory lock and only the leader performs
the closed-loop mitigation.
"""

import threading
import time

from app.core.config import settings
from app.core.observability import emit_event
from app.core.reliability.leader import LeaderLock, release, try_acquire
from app.core.reliability.remediation import _write_override
from app.core.reliability.slo_window import rolling_slo


DEFAULT_LOCK_KEY = 914_002_777  # stable constant for this demo repo


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
                    emit_event("remediation_leader_acquired", {"lock_key": lock_key})
                elif not acquired and is_leader:
                    # Lost leadership.
                    is_leader = False
                    violated = 0
                    emit_event("remediation_leader_lost", {"lock_key": lock_key})

            if not is_leader:
                time.sleep(check_every_s)
                continue

            try:
                snap = rolling_slo.snapshot()
                if int(snap.get("samples", 0)) < int(min_samples):
                    time.sleep(check_every_s)
                    continue

                bad = (
                    snap["error_rate"] >= float(error_rate_threshold)
                    or snap["unknown_rate"] >= float(unknown_rate_threshold)
                    or snap["p95_latency_ms"] >= float(max_request_latency_ms)
                )

                violated = violated + 1 if bad else max(0, violated - 1)

                if violated >= 3:
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

            except Exception as e:
                emit_event("remediation_error", {"error": str(e)})

            time.sleep(check_every_s)

    def _cleanup() -> None:
        try:
            release(lock)
        except Exception:
            pass

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
