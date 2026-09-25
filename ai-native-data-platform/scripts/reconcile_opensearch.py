from __future__ import annotations

import argparse
import json

from app.opensearch.reconcile import reconcile_all_workspaces, reconcile_workspace


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Repair chunks missing from OpenSearch (dual-write drift) by re-driving them from Postgres."
    )
    ap.add_argument("--workspace", default=None, help="Reconcile a single workspace_id. Omit to reconcile all.")
    ap.add_argument("--batch-size", type=int, default=500, help="Postgres scan batch size")
    args = ap.parse_args()

    if args.workspace:
        reports = [reconcile_workspace(args.workspace, batch_size=args.batch_size)]
    else:
        reports = reconcile_all_workspaces(batch_size=args.batch_size)

    print(json.dumps([r.as_dict() for r in reports], indent=2))


if __name__ == "__main__":
    main()
