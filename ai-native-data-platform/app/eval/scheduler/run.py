from __future__ import annotations

"""Distributed evaluation scheduler.

This is a minimal, dependency-free "scheduler" that can parallelize evaluation
over multiple workers (processes) and merge outputs.

It is intentionally simple (no Celery/KubeFlow dependency) but shows the
platform-level concept that evaluation jobs are schedulable and mergeable.

Example:
  python -m app.eval.scheduler.run --experiment app/eval/experiments/baseline.yaml \
    --cases app/eval/datasets/cases.jsonl --num_shards 8
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--num_shards", type=int, default=4)
    ap.add_argument("--out_dir", default="artifacts/distributed")
    args = ap.parse_args()

    exp = Path(args.experiment)
    cases = Path(args.cases)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    procs: list[subprocess.Popen] = []
    shard_paths: list[Path] = []

    for i in range(int(args.num_shards)):
        out = out_dir / f"eval_shard_{i}.json"
        shard_paths.append(out)
        cmd = [
            sys.executable,
            "-m",
            "app.eval.run",
            "--experiment",
            exp.as_posix(),
            "--cases",
            cases.as_posix(),
            "--json_out",
            out.as_posix(),
            "--shard_idx",
            str(i),
            "--num_shards",
            str(int(args.num_shards)),
        ]
        procs.append(subprocess.Popen(cmd))

    rc = 0
    for p in procs:
        r = p.wait()
        rc = rc or r

    # Merge shard summaries into one file for tracking.
    merged = {"shards": [], "gates_ok": True}
    for sp in shard_paths:
        if not sp.exists():
            merged["gates_ok"] = False
            continue
        data = json.loads(sp.read_text(encoding="utf-8"))
        merged["shards"].append({"path": sp.as_posix(), "summary": data})
        if not data.get("gates_ok", True):
            merged["gates_ok"] = False

    merged_path = out_dir / "eval_merged.json"
    merged_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    if rc != 0 or not merged.get("gates_ok", True):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
