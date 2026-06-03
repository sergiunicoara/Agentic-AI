#!/usr/bin/env python
"""OpenSearch index initialisation script.

Usage:
    python scripts/opensearch_init.py [--url http://localhost:9200] [--index ai_platform_chunks] [--recreate]

Run after docker compose up to ensure the index exists with correct mappings.
Safe to run multiple times — create_if_missing() is idempotent.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# Allow running from project root without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def wait_for_opensearch(url: str, retries: int = 20, delay: float = 3.0) -> None:
    import httpx
    print(f"Waiting for OpenSearch at {url} ...", flush=True)
    for i in range(retries):
        try:
            r = httpx.get(f"{url}/_cluster/health", timeout=5)
            status = r.json().get("status", "")
            if status in ("green", "yellow"):
                print(f"  ✓ OpenSearch ready (status={status})", flush=True)
                return
        except Exception:
            pass
        print(f"  attempt {i+1}/{retries} — not ready yet, retrying in {delay}s", flush=True)
        time.sleep(delay)
    raise RuntimeError(f"OpenSearch at {url} did not become healthy after {retries} attempts")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise OpenSearch index for ai-native-data-platform")
    parser.add_argument("--url", default=os.getenv("OPENSEARCH_URL", "http://localhost:9200"))
    parser.add_argument("--index", default=os.getenv("OPENSEARCH_INDEX", "ai_platform_chunks"))
    parser.add_argument("--recreate", action="store_true", help="Drop and recreate index (destructive)")
    parser.add_argument("--wait", action="store_true", help="Wait for OpenSearch to be healthy before creating index")
    args = parser.parse_args()

    # Patch settings so the module picks up CLI args.
    os.environ["OPENSEARCH_URL"] = args.url
    os.environ["OPENSEARCH_INDEX"] = args.index

    if args.wait:
        wait_for_opensearch(args.url)

    from app.opensearch.client import get_client, is_available
    from app.opensearch.index import create_if_missing, delete_index, health

    print(f"\nConnecting to OpenSearch: {args.url}", flush=True)
    client = get_client()

    if not is_available():
        print("ERROR: OpenSearch is not available", file=sys.stderr)
        sys.exit(1)

    if args.recreate:
        print(f"Deleting index '{args.index}' ...", flush=True)
        delete_index(client)

    created = create_if_missing(client)
    if created:
        print(f"✓ Index '{args.index}' created", flush=True)
    else:
        print(f"✓ Index '{args.index}' already exists — no changes", flush=True)

    h = health(client)
    print(f"  cluster status: {h.get('status')} | shards: {h.get('active_shards')}", flush=True)
    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
