from __future__ import annotations

import argparse
import json
from statistics import mean


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = int(round((len(values) - 1) * q))
    idx = min(max(idx, 0), len(values) - 1)
    return float(values[idx])


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze soak_ask.py JSONL output")
    ap.add_argument("--in", dest="in_path", required=True)
    args = ap.parse_args()

    lats: list[float] = []
    oks = 0
    unknowns = 0
    total = 0

    with open(args.in_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            row = json.loads(line)
            if int(row.get("status") or 0) == 200:
                oks += 1
                lats.append(float(row.get("latency_ms") or 0.0))
                if row.get("unknown"):
                    unknowns += 1

    print(
        json.dumps(
            {
                "total": total,
                "ok": oks,
                "error_rate": round(1 - (oks / max(1, total)), 4),
                "unknown_rate": round(unknowns / max(1, oks), 4),
                "mean_ms": round(mean(lats), 2) if lats else 0.0,
                "p50_ms": round(pct(lats, 0.50), 2),
                "p95_ms": round(pct(lats, 0.95), 2),
                "p99_ms": round(pct(lats, 0.99), 2),
                "max_ms": round(max(lats), 2) if lats else 0.0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
