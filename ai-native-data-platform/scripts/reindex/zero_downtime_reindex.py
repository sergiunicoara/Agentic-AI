#!/usr/bin/env python3
"""Zero-downtime embedding reindex with SLO-based cutover + rollback.

Design goals:
- Idempotent backfill (safe to resume)
- Canary validation against latency/error budgets
- Atomic cutover (active_embedding_version swap) with rollback primitive

Requires:
- ops/sql/001_workspace_index_state.sql applied
- API started with ALLOW_EMBEDDING_OVERRIDE=true and ADMIN_TOKEN set

Example:
  python scripts/reindex/zero_downtime_reindex.py \
    --base-url http://localhost:8000 \
    --workspace demo \
    --api-key demo \
    --target v2 \
    --rate 30 --duration 60 --p95-ms 260 --err-rate 0.02
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app.indexing.index_state import (
    clear_target_embedding_version,
    get_index_state,
    promote_target_to_active,
    set_active_embedding_version,
    set_target_embedding_version,
)
from app.indexing.pipeline import IndexingConfig, build_manifest, run_manifest


def _run_k6(*, base_url: str, workspace_id: str, api_key: str, rate: int, duration_s: int, embedding_version: str, admin_token: str) -> Path:
    outdir = Path("reports")
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"k6_canary_{workspace_id}_{embedding_version}_{int(time.time())}.json"

    env = os.environ.copy()
    env.update(
        {
            "BASE_URL": base_url,
            "WORKSPACE_ID": workspace_id,
            "API_KEY": api_key,
            "RATE": str(rate),
            "DURATION": f"{duration_s}s",
            "EMBEDDING_VERSION_OVERRIDE": embedding_version,
            "ADMIN_TOKEN": admin_token,
        }
    )

    cmd = [
        "k6",
        "run",
        "loadtest/k6/retrieval.js",
        f"--summary-export={out}",
    ]
    subprocess.check_call(cmd, env=env)
    return out


def _read_metric(summary: dict, metric: str, key: str) -> float:
    m = summary.get("metrics", {}).get(metric, {})
    vals = m.get("values") or m
    v = vals.get(key)
    return float(v or 0.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--target", required=True, help="target embedding_version tag")
    ap.add_argument("--rate", type=int, default=30)
    ap.add_argument("--duration", type=int, default=60, help="seconds")
    ap.add_argument("--p95-ms", type=float, default=260.0)
    ap.add_argument("--p99-ms", type=float, default=450.0)
    ap.add_argument("--err-rate", type=float, default=0.02)
    ap.add_argument("--admin-token", default=os.environ.get("ADMIN_TOKEN", ""))
    ap.add_argument("--fault-injection", type=float, default=0.0)
    ap.add_argument("--max-retries", type=int, default=5)
    args = ap.parse_args()

    if not args.admin_token:
        print("ERROR: --admin-token (or ADMIN_TOKEN env var) is required for canary override.", file=sys.stderr)
        return 2

    st = get_index_state(args.workspace)
    prev_active = st.active_embedding_version

    print(f"Current active embedding_version={prev_active}; target={args.target}")

    # 1) Set target
    set_target_embedding_version(args.workspace, args.target)

    # 2) Backfill target version
    manifest = build_manifest(workspace_id=args.workspace)
    cfg = IndexingConfig()
    cfg = IndexingConfig(
        batch_size_docs=cfg.batch_size_docs,
        batch_size_chunks=cfg.batch_size_chunks,
        embedding_batch_size=cfg.embedding_batch_size,
        statement_timeout_ms=cfg.statement_timeout_ms,
        manifest_dir=cfg.manifest_dir,
        fault_injection_rate=float(args.fault_injection),
        max_retries=int(args.max_retries),
        max_backoff_ms=5000,
    )

    print(f"Backfilling chunks for embedding_version={args.target} from manifest={manifest}")
    result = run_manifest(str(manifest), workspace_id=args.workspace, cfg=cfg, embedding_version=args.target)
    Path("reports").mkdir(parents=True, exist_ok=True)
    Path("reports") / ""
    with open(Path("reports") / f"reindex_{args.workspace}_{args.target}_{int(time.time())}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # 3) Canary retrieval using override header (via k6 env)
    print("Running canary loadtest against target embedding_version...")
    summary_path = _run_k6(
        base_url=args.base_url,
        workspace_id=args.workspace,
        api_key=args.api_key,
        rate=args.rate,
        duration_s=args.duration,
        embedding_version=args.target,
        admin_token=args.admin_token,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    p95 = _read_metric(summary, "http_req_duration", "p(95)")
    p99 = _read_metric(summary, "http_req_duration", "p(99)")
    err = _read_metric(summary, "http_req_failed", "rate")

    print(f"Canary results: p95={p95:.1f}ms p99={p99:.1f}ms err_rate={err:.4f}")

    ok = (p95 <= args.p95_ms) and (p99 <= args.p99_ms) and (err <= args.err_rate)

    if not ok:
        print("Canary FAILED. Rolling back target and keeping previous active.")
        clear_target_embedding_version(args.workspace)
        set_active_embedding_version(args.workspace, prev_active)
        return 3

    # 4) Cutover
    print("Canary OK. Promoting target to active.")
    promote_target_to_active(args.workspace)

    print("Cutover complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
