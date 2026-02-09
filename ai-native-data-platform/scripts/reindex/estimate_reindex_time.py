#!/usr/bin/env python3
"""Estimate embedding reindex duration for a workspace.

Two modes:
- `--from-recent-report reports/*.json`: uses a prior bulk index result (docs/chunks + duration)
- `--assume-chunks-per-doc` + `--throughput-chunks-per-s`

This is intentionally approximate, but it makes reindex capacity planning explicit.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path

from sqlalchemy import text

from app.data.db import session_scope


def _count_docs(workspace_id: str) -> int:
    with session_scope() as db:
        row = db.execute(
            text("SELECT count(*) FROM document WHERE workspace_id=:w"),
            {"w": workspace_id},
        ).first()
    return int(row[0] if row else 0)


def _load_report(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--report", default="", help="path to a bulk index report JSON")
    ap.add_argument("--assume-chunks-per-doc", type=float, default=6.0)
    ap.add_argument("--throughput-chunks-per-s", type=float, default=120.0)
    args = ap.parse_args()

    docs = _count_docs(args.workspace)

    if args.report:
        rep = _load_report(args.report)
        dur = float(rep.get("duration_s") or 0.0)
        chunks = float(rep.get("indexed_chunks") or 0.0)
        if dur > 0 and chunks > 0:
            tput = chunks / dur
            est_chunks = docs * float(args.assume_chunks_per_doc)
            est_s = est_chunks / tput
            print(f"docs={docs}  baseline_throughput={tput:.2f} chunks/s  est_chunks={est_chunks:.0f}  est_duration={est_s/60:.1f} min")
            return 0

    est_chunks = docs * float(args.assume_chunks_per_doc)
    est_s = est_chunks / float(args.throughput_chunks_per_s)
    print(f"docs={docs}  assumed_chunks_per_doc={args.assume_chunks_per_doc}  assumed_throughput={args.throughput_chunks_per_s} chunks/s")
    print(f"est_chunks={est_chunks:.0f}  est_duration={est_s/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
