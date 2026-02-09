from __future__ import annotations

"""Render evaluation summary into a README-friendly snapshot.

CI produces artifacts/eval_summary.json. This script generates a compact
Markdown table that can be embedded in the README or uploaded as a separate
artifact.
"""

import argparse
import json
from pathlib import Path


def render(summary: dict) -> str:
    exp = summary.get("experiment", {})
    name = exp.get("name") or summary.get("experiment_name") or "unknown"
    gates = summary.get("gates", {})
    metrics = summary.get("metrics", {})

    rows = []
    def add(label: str, key: str, fmt: str = "{:.3f}"):
        val = metrics.get(key)
        if val is None:
            return
        if isinstance(val, (int, float)):
            rows.append((label, fmt.format(float(val))))
        else:
            rows.append((label, str(val)))

    add("Pass rate", "pass_rate", "{:.3f}")
    add("Recall@k (mean)", "recall_mean", "{:.3f}")
    add("MRR (mean)", "mrr_mean", "{:.3f}")
    add("Latency p95 (ms)", "latency_p95_ms", "{:.0f}")
    add("Unknown rate", "unknown_rate", "{:.3f}")
    add("Gen failure rate", "generation_failure_rate", "{:.3f}")

    # Optional significance output
    sig = summary.get("significance", {})
    sig_line = ""
    if sig:
        delta = sig.get("delta_pass_rate")
        p = sig.get("p_value")
        if delta is not None and p is not None:
            sig_line = f"\n\n**Vs baseline:** Δ pass-rate={delta:+.3f}, p={p:.4f}"

    gate_line = "✅ gates passed" if gates.get("passed") else "❌ gates failed"

    table = "\n".join(["| Metric | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows])
    return (
        f"### Results Snapshot ({name})\n\n"
        f"{gate_line}\n\n"
        f"{table}"
        f"{sig_line}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_json", required=True)
    ap.add_argument("--out_md", required=True)
    args = ap.parse_args()

    summary = json.loads(Path(args.in_json).read_text(encoding="utf-8"))
    md = render(summary)
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
