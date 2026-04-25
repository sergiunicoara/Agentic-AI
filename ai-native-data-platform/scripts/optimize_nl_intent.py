#!/usr/bin/env python
"""Optimize the NL→SQL intent extractor using DSPy BootstrapFewShot.

Run once (or after the golden dataset changes):

    python scripts/optimize_nl_intent.py

Output: app/nl_query/compiled_intent.json
        Loaded automatically by get_extractor() at runtime.

Requirements:
    - OPENAI_API_KEY set in environment or .env
    - uv pip install dspy-ai
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Make sure project root is on sys.path when run as a script.
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import yaml
import dspy
from dspy.teleprompt import BootstrapFewShot

from app.nl_query.intent import QueryIntent
from app.nl_query.sql_builder import build_sql

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GOLDEN_PATH = ROOT / "app" / "eval" / "datasets" / "nl_query_golden.yaml"
COMPILED_PATH = ROOT / "app" / "nl_query" / "compiled_intent.json"
_EVAL_WORKSPACE = "__dspy_eval__"

# ---------------------------------------------------------------------------
# SQL normalization — makes comparison whitespace- and param-name-agnostic
# ---------------------------------------------------------------------------


def _normalize(sql: str) -> str:
    sql = sql.lower().strip()
    # Collapse all whitespace (including newlines from YAML block scalars).
    sql = re.sub(r"\s+", " ", sql)
    # Normalize all named params → ? so param ordering doesn't matter.
    sql = re.sub(r":\w+", "?", sql)
    # Treat ILIKE and LIKE as equivalent — both are valid for text search.
    sql = sql.replace(" ilike ", " like ")
    return sql


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------


def sql_match(example: dspy.Example, pred: dspy.Prediction, trace=None) -> bool:  # type: ignore[type-arg]
    """Return True if the predicted intent produces the expected SQL."""
    try:
        intent: QueryIntent = pred.intent  # set by IntentExtractor.forward()
        got_sql, _ = build_sql(intent, workspace_id=_EVAL_WORKSPACE)
        got = _normalize(got_sql)
        want = _normalize(example.expected_sql)
        match = got == want
        if not match:
            # Always print mismatches — the main signal for fixing the dataset
            # or normalization rules.
            print(f"\n  [mismatch] {example.nl_query!r}")
            print(f"    want: {want}")
            print(f"    got:  {got}")
        return match
    except Exception as exc:
        print(f"\n  [metric error] {example.nl_query!r} → {exc}")
        return False


# ---------------------------------------------------------------------------
# Load golden dataset
# ---------------------------------------------------------------------------


def load_trainset() -> list[dspy.Example]:
    raw = yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8"))
    trainset = []
    for item in raw["examples"]:
        ex = dspy.Example(
            nl_query=item["nl_query"].strip(),
            expected_sql=item["expected_sql"].strip(),
        ).with_inputs("nl_query")
        trainset.append(ex)
    return trainset


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------


def main() -> None:
    # Load .env if present.
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set. Export it or add it to .env")
        sys.exit(1)

    # Disable DSPy LLM cache for this script — previous runs cached stale
    # outputs from before the normalization fixes were in place.
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    lm = dspy.LM(f"openai/{model}", api_key=api_key, cache=False)
    dspy.configure(lm=lm)

    # Import AFTER dspy.configure so get_extractor() picks up the LM.
    from app.nl_query.dspy_intent import IntentExtractor

    trainset = load_trainset()
    print(f"Loaded {len(trainset)} golden examples from {GOLDEN_PATH}")

    # Split: 80% train, 20% dev.
    split = max(1, int(len(trainset) * 0.8))
    train, dev = trainset[:split], trainset[split:]
    print(f"  train={len(train)}  dev={len(dev)}")

    teleprompter = BootstrapFewShot(
        metric=sql_match,
        max_bootstrapped_demos=4,
        max_labeled_demos=4,
        max_rounds=1,
    )

    print("Running BootstrapFewShot optimization …")
    compiled = teleprompter.compile(
        IntentExtractor(),
        trainset=train,
    )

    # Evaluate on dev set.
    if dev:
        correct = sum(
            sql_match(ex, compiled(nl_query=ex.nl_query))
            for ex in dev
        )
        print(f"\nDev accuracy: {correct}/{len(dev)} = {correct / len(dev):.0%}")

    COMPILED_PATH.parent.mkdir(parents=True, exist_ok=True)
    compiled.save(str(COMPILED_PATH))
    print(f"Saved compiled module → {COMPILED_PATH}")
    print("The module is loaded automatically by get_extractor() at runtime.")


if __name__ == "__main__":
    main()
