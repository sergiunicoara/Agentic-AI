#!/usr/bin/env python3
"""Compare a k6 --summary-export JSON file against a stored baseline.

This is intentionally dependency-free so it can run in CI.

Usage:
  python scripts/perf/compare_k6_baseline.py --current out.json --baseline perf/baselines/retrieval.json

Exit codes:
  0  pass
  2  regression detected
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Threshold:
    metric: str
    key: str
    # For latency metrics, lower is better; for rate metrics, higher is worse.
    direction: str  # "lower" | "higher"
    max_regression_pct: float


DEFAULT_THRESHOLDS: list[Threshold] = [
    Threshold("http_req_duration", "p(95)", "lower", 10.0),
    Threshold("http_req_duration", "p(99)", "lower", 10.0),
    Threshold("http_req_failed", "rate", "higher", 25.0),
]


def _load(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get(summary: dict[str, Any], metric: str, key: str) -> float | None:
    m = summary.get("metrics", {}).get(metric, {})
    # k6 uses both 'values' and 'thresholds' depending on version
    vals = m.get("values") or m
    v = vals.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _pct_change(curr: float, base: float) -> float:
    if base == 0:
        return math.inf if curr != 0 else 0.0
    return (curr - base) / base * 100.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--thresholds", default="")
    args = ap.parse_args()

    current = _load(args.current)
    baseline = _load(args.baseline)

    thresholds = DEFAULT_THRESHOLDS

    failures: list[str] = []

    for th in thresholds:
        c = _get(current, th.metric, th.key)
        b = _get(baseline, th.metric, th.key)
        if c is None or b is None:
            failures.append(f"missing metric {th.metric}.{th.key} (current={c}, baseline={b})")
            continue

        change = _pct_change(c, b)

        # For 'lower is better', regression is positive change.
        # For 'higher is worse' (rates), regression is positive change.
        regression = change
        if th.direction not in ("lower", "higher"):
            failures.append(f"bad threshold direction for {th.metric}.{th.key}: {th.direction}")
            continue

        if regression > th.max_regression_pct:
            failures.append(
                f"regression {th.metric}.{th.key}: baseline={b:.4g} current={c:.4g} change={change:.2f}% (allowed {th.max_regression_pct:.1f}%)"
            )

    if failures:
        print("PERF REGRESSION DETECTED")
        for f in failures:
            print("-", f)
        return 2

    print("PERF OK (no regressions vs baseline)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
