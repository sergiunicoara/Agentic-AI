from __future__ import annotations

"""Automated remediation loop.

This module demonstrates a simple closed-loop ops pattern:

  observe rolling SLOs -> detect sustained violation -> apply mitigation

Mitigations are conservative and reversible:
  - force all traffic to a safe control experiment (A/B override)

In a production platform this logic would likely live in a separate controller
service and interact with a feature flag system / deployment system.
"""

import json
import threading
import time
from pathlib import Path

from app.core.config import settings
from app.core.observability import emit_event
from app.core.reliability.slo_window import rolling_slo


_override_path = Path(".runtime/ab_override.json")


def _write_override(experiment: str) -> None:
    _override_path.parent.mkdir(parents=True, exist_ok=True)
    _override_path.write_text(json.dumps({"force_all": experiment, "ts": time.time()}), encoding="utf-8")


def clear_override() -> None:
    if _override_path.exists():
        _override_path.unlink()


def start_remediation_loop(
    *,
    error_rate_threshold: float = 0.25,
    unknown_rate_threshold: float = 0.35,
    p95_latency_threshold_ms: float | None = None,
    min_samples: int = 200,
    check_every_s: float = 5.0,
    force_experiment: str | None = None,
) -> None:
    """Start a background loop.

    The loop applies a remediation override when a sustained violation is
    detected. The remediation is reversible: removing the override re-enables
    normal routing.
    """

    force_experiment = force_experiment or settings.ab_default_experiment
    if p95_latency_threshold_ms is None:
        p95_latency_threshold_ms = float(settings.max_request_latency_ms) * 1.25

    def _loop() -> None:
        # Small hysteresis to avoid flapping.
        violated = 0
        while True:
            try:
                snap = rolling_slo.snapshot()
                bad = (
                    snap["error_rate"] >= float(error_rate_threshold)
                    or snap["unknown_rate"] >= float(unknown_rate_threshold)
                    or snap["p95_latency_ms"] >= float(p95_latency_threshold_ms)
                )
                if bad:
                    violated += 1
                else:
                    violated = max(0, violated - 1)

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
                                "p95_latency_ms": p95_latency_threshold_ms,
                            },
                        },
                    )
                    # Once applied, keep monitoring; allow manual clear.
                    time.sleep(check_every_s)
                    continue

            except Exception:
                pass

            time.sleep(check_every_s)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
