"""Run the large-corpus indexing pipeline.

Examples:
  python scripts/run_bulk_index.py --workspace ws_123 --build-manifest
  python scripts/run_bulk_index.py --workspace ws_123 --manifest data/index_manifests/manifest_...jsonl
"""

from __future__ import annotations

import argparse
import json

from app.indexing import build_manifest, run_manifest


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True, help="Workspace id")
    p.add_argument("--build-manifest", action="store_true")
    p.add_argument("--manifest", default="", help="Path to manifest jsonl")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--embedding-version", default="", help="Override embedding_version tag")
    p.add_argument("--out", default="", help="Write run report JSON to this path (default: reports/...) ")
    args = p.parse_args()

    m = args.manifest
    if args.build_manifest:
        mpath = build_manifest(workspace_id=args.workspace, limit=(args.limit or None))
        m = str(mpath)
        print(m)

    if not m:
        raise SystemExit("Either --build-manifest or --manifest must be provided")

    result = run_manifest(m, workspace_id=args.workspace, embedding_version=(args.embedding_version or None))
    print(json.dumps(result, indent=2))

    out = args.out
    if not out:
        Path("reports").mkdir(parents=True, exist_ok=True)
        import time
        out = f"reports/bulk_index_{args.workspace}_{int(time.time())}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote report: {out}")


if __name__ == "__main__":
    main()
