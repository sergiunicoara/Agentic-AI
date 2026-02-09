#!/usr/bin/env python3
"""Generate simple plots from a k6 summary-export JSON.

Produces:
- reports/<name>_latency.png : p50/p90/p95/p99 bar chart
- reports/<name>_rates.png   : error rate + checks

Usage:
  python scripts/perf/plot_k6_summary.py --summary out.json --name retrieval

This is meant for local/CI artifact generation. In CI environments without
matplotlib, you can skip this step and still compare baselines.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _get(metrics: dict, metric: str, key: str):
    m = metrics.get(metric, {})
    vals = m.get("values") or m
    return vals.get(key)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--outdir", default="reports")
    args = ap.parse_args()

    with open(args.summary, "r", encoding="utf-8") as f:
        summary = json.load(f)

    metrics = summary.get("metrics", {})

    # Lazy import so baseline compare can run without matplotlib.
    import matplotlib.pyplot as plt  # type: ignore

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Latency chart
    ps = ["p(50)", "p(90)", "p(95)", "p(99)"]
    vals = [float(_get(metrics, "http_req_duration", p) or 0.0) for p in ps]

    plt.figure()
    plt.bar(ps, vals)
    plt.ylabel("ms")
    plt.title(f"{args.name}: http_req_duration percentiles")
    plt.tight_layout()
    plt.savefig(outdir / f"{args.name}_latency.png")
    plt.close()

    # Rates chart
    keys = ["http_req_failed.rate", "checks.rate"]
    rvals = [
        float(_get(metrics, "http_req_failed", "rate") or 0.0),
        float(_get(metrics, "checks", "rate") or 0.0),
    ]

    plt.figure()
    plt.bar(keys, rvals)
    plt.ylabel("rate")
    plt.title(f"{args.name}: error/check rates")
    plt.tight_layout()
    plt.savefig(outdir / f"{args.name}_rates.png")
    plt.close()

    print(f"Wrote plots to {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
