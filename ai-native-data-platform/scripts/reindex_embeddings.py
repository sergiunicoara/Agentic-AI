from __future__ import annotations

import argparse

from app.indexing.lifecycle import reindex_embeddings


def main() -> None:
    ap = argparse.ArgumentParser(description="Zero-downtime embedding reindex with cutover")
    ap.add_argument("--workspace", required=True, help="workspace_id")
    ap.add_argument("--target-version", required=True, help="embedding version tag to write and promote")
    ap.add_argument("--limit", type=int, default=None, help="optional doc limit for canary")
    args = ap.parse_args()

    res = reindex_embeddings(workspace_id=args.workspace, target_embedding_version=args.target_version, limit=args.limit)
    print(res)


if __name__ == "__main__":
    main()
