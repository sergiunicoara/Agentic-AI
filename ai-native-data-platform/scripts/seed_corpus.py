#!/usr/bin/env python3
"""Seed a synthetic corpus for local perf tests.

This is intentionally deterministic and dependency-free.

Usage:
  DATABASE_URL=... python scripts/seed_corpus.py --workspace demo --docs 500
"""

from __future__ import annotations

import argparse
import random
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.data.db import write_session_scope

TOPICS = [
    "incident response", "access control", "API key rotation", "observability", "sharding", "evaluation harness", "reliability", "backfill pipelines"
]


def _doc_text(i: int) -> str:
    rnd = random.Random(i)
    topic = TOPICS[i % len(TOPICS)]
    bullets = []
    for j in range(12):
        bullets.append(f"- {topic}: guideline {j} with detail {rnd.randint(1,9999)} and rationale.")
    return "\n".join(bullets)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--docs", type=int, default=300)
    ap.add_argument("--source", default="seed")
    args = ap.parse_args()

    with write_session_scope() as db:
        for i in range(int(args.docs)):
            doc_id = str(uuid.uuid4())
            db.execute(
                text(
                    """
                    INSERT INTO document (id, workspace_id, source_name, external_id, title, text)
                    VALUES (:id, :w, :s, :e, :t, :x)
                    ON CONFLICT (workspace_id, source_name, external_id) DO NOTHING
                    """
                ),
                {
                    "id": doc_id,
                    "w": args.workspace,
                    "s": args.source,
                    "e": f"{args.source}-{i}",
                    "t": f"Policy Note {i}",
                    "x": _doc_text(i),
                },
            )

    print(f"Seeded up to {args.docs} docs into workspace={args.workspace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
