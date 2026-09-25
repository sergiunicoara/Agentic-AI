#!/usr/bin/env python3
"""Seed the fixed 'demo' workspace with content the eval golden dataset
(app/eval/datasets/cases.jsonl) actually depends on.

Unlike scripts/seed_corpus.py (synthetic, randomized load-test data with no
relation to any golden query), this seeds one deterministic document whose
text is written to satisfy case 1's query ("What is the biggest customer
pain point?") via real lexical (Postgres FTS) retrieval, and to trigger the
mock LLM's "onboarding" answer branch (app/providers/llm.py) so the eval
harness's pass_rate / rubric_pass_rate / groundedness_mean gates are
checking real behavior instead of running against an empty workspace and
scoring vacuous zeros.

Case 2 ("What is the contract value?", expect_unknown=True) needs no
seeding: app/eval/run.py only invokes generation when expect_unknown is
False, so it passes unconditionally as long as the workspace has no content
that would somehow make expect_unknown wrong.

This calls the real ingestion pipeline (app.ingestion.pipeline.process_document)
rather than hand-writing rows, so it exercises the same chunk/embed/insert
path production traffic uses, and is idempotent via the same
(workspace_id, source_name, external_id) conflict key normal ingestion uses.

Usage:
  DATABASE_URL=... python scripts/seed_eval_corpus.py --workspace demo
"""

from __future__ import annotations

import argparse
import uuid

from sqlalchemy import text

from app.data.db import workspace_session_scope
from app.ingestion.pipeline import process_document

_SOURCE = "eval-seed"
_EXTERNAL_ID = "customer-feedback-summary"
_TITLE = "Customer Feedback Summary"
# Written to share vocabulary with case 1's query ("biggest", "customer",
# "pain", "point") for strong lexical (FTS) ranking, and to place
# "onboarding" with comfortably more than 40 characters of text on each
# side within its chunk — the mock LLM's onboarding branch builds a
# citation snippet as a +/-40-char window around that word, and
# evidence_minimum() requires >= 80 total citation characters.
_TEXT = (
    "We collected structured feedback from twenty enterprise customers this "
    "quarter, and across nearly every interview one theme dominated the "
    "conversation: the biggest customer pain point is onboarding friction "
    "and setup complexity during the first week after signup. Support "
    "tickets filed in the first seven days are dominated by onboarding "
    "confusion, environment setup errors, and unclear first-run "
    "instructions. Reducing onboarding friction is the top product "
    "priority for next quarter."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="demo")
    args = ap.parse_args()

    with workspace_session_scope(args.workspace, write=True) as db:
        row = db.execute(
            text(
                """
                INSERT INTO document (id, workspace_id, source_name, external_id, title, text)
                VALUES (:id, :w, :s, :e, :t, :x)
                ON CONFLICT (workspace_id, source_name, external_id) DO NOTHING
                RETURNING id::text
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "w": args.workspace,
                "s": _SOURCE,
                "e": _EXTERNAL_ID,
                "t": _TITLE,
                "x": _TEXT,
            },
        ).first()
        if row is None:
            row = db.execute(
                text(
                    """
                    SELECT id::text FROM document
                    WHERE workspace_id=:w AND source_name=:s AND external_id=:e
                    """
                ),
                {"w": args.workspace, "s": _SOURCE, "e": _EXTERNAL_ID},
            ).first()
        doc_id = row[0]

    # Chunk, embed, and persist synchronously (the same code path the
    # durable worker runs — CI doesn't start app.worker_main separately).
    process_document(doc_id, args.workspace)
    print(f"Seeded + ingested eval corpus doc {doc_id} into workspace={args.workspace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
