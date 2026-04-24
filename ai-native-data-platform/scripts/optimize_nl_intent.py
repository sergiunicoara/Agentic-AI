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

from app.nl_query.dspy_intent import IntentExtractor, NLToIntent, _configure_dspy
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
    # Normalize positional param names (:_v0, :_v1_2 …) → ?
    sql = re.sub(r":_v\d+(?:_\d+)?", "?", sql)
    return sql


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------


def sql_match(example: dspy.Example, pred: dspy.Prediction, trace=None) -> bool:  # type: ignore[type-arg]
    """Return True if the predicted intent produces the expected SQL."""
    try:
        raw = pred.intent_json.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        import json
        data = json.loads(raw.strip())
        intent = QueryIntent.model_validate(data)
        sql, _ = build_sql(intent, workspace_id=_EVAL_WORKSPACE)
        return _normalize(sql) == _normalize(example.expected_sql)
    except Exception as exc:
        if trace is not None:
            print(f"  [metric error] {exc}")
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

    _configure_dspy()

    trainset = load_trainset()
    print(f"Loaded {len(trainset)} golden examples from {GOLDEN_PATH}")

    # Split: 80% train, 20% dev (used internally by BootstrapFewShot).
    split = max(1, int(len(trainset) * 0.8))
    train, dev = trainset[:split], trainset[split:]
    print(f"  train={len(train)}  dev={len(dev)}")

    teleprompter = BootstrapFewShot(
        metric=sql_match,
        max_bootstrapped_demos=4,   # few-shot examples injected into prompt
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
        print(f"Dev accuracy: {correct}/{len(dev)} = {correct / len(dev):.0%}")

    COMPILED_PATH.parent.mkdir(parents=True, exist_ok=True)
    compiled.save(str(COMPILED_PATH))
    print(f"Saved compiled module → {COMPILED_PATH}")
    print("The module is loaded automatically by get_extractor() at runtime.")


if __name__ == "__main__":
    main()
