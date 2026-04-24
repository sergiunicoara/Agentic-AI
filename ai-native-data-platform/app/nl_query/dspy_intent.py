from __future__ import annotations

"""DSPy-powered intent extractor for NL → SQL.

Replaces the hand-written _SYSTEM_PROMPT in intent.py with a DSPy Signature
whose instructions are discovered automatically by BootstrapFewShot (see
scripts/optimize_nl_intent.py).

Usage:
  - At runtime:  get_extractor() returns a singleton (loads compiled_intent.json
                 if present, falls back to zero-shot with the typed signature).
  - Optimization: run scripts/optimize_nl_intent.py once; it saves
                  compiled_intent.json next to this file.
"""

import json
import threading
from pathlib import Path

import dspy

from app.nl_query.intent import (
    ALLOWED_SCHEMA,
    Filter,
    OrderBy,
    QueryIntent,
    _SCHEMA_CONTEXT,
)

# ---------------------------------------------------------------------------
# DSPy Signature — replaces _SYSTEM_PROMPT
# ---------------------------------------------------------------------------

_TABLES = ", ".join(ALLOWED_SCHEMA.keys())
_FILTER_OPS = "=, !=, >, <, >=, <=, LIKE, ILIKE, IN, IS NULL, IS NOT NULL"

_INTENT_SCHEMA = (
    '{"table": str, "select_columns": [str], '
    '"filters": [{"column": str, "operator": str, "value": any}], '
    '"aggregation": str|null, "aggregation_column": str|null, '
    '"group_by": [str], '
    '"order_by": {"column": str, "direction": "ASC"|"DESC"}|null, '
    '"limit": int}'
)


class NLToIntent(dspy.Signature):
    f"""Extract a structured SQL query intent from a natural language question
    about a RAG data platform.

    Available tables and columns:
    {_SCHEMA_CONTEXT}

    Rules:
    - table must be one of: {_TABLES}
    - select_columns: list of column names; [] means all columns for that table.
    - filters: list of WHERE conditions; operator must be one of: {_FILTER_OPS}.
    - aggregation: COUNT | SUM | AVG | MIN | MAX | null.
    - aggregation_column: column to aggregate; omit (null) for COUNT(*).
    - group_by: columns for GROUP BY when using aggregation.
    - order_by: sort spec or null.
    - limit: integer 1–1000, default 100.
    - Only use columns listed above for the chosen table.
    - Return ONLY valid JSON — no markdown fences, no explanation.
    """

    nl_query: str = dspy.InputField(
        desc="Natural language question about the data platform"
    )
    intent_json: str = dspy.OutputField(
        desc=f"JSON object matching schema: {_INTENT_SCHEMA}"
    )


# ---------------------------------------------------------------------------
# DSPy Module
# ---------------------------------------------------------------------------


class IntentExtractor(dspy.Module):
    """ChainOfThought extractor — reasoning step improves structured accuracy."""

    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.ChainOfThought(NLToIntent)

    def forward(self, nl_query: str) -> QueryIntent:  # type: ignore[override]
        result = self.predict(nl_query=nl_query)
        raw = result.intent_json.strip()
        # Strip accidental markdown fences the LLM sometimes emits.
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        return QueryIntent.model_validate(data)


# ---------------------------------------------------------------------------
# Configuration helper
# ---------------------------------------------------------------------------

_COMPILED_PATH = Path(__file__).parent / "compiled_intent.json"


def _configure_dspy() -> None:
    """Wire DSPy to the same OpenAI model used by the rest of the platform."""
    import os

    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    lm = dspy.LM(f"openai/{model}", api_key=api_key)
    dspy.configure(lm=lm)


# ---------------------------------------------------------------------------
# Thread-safe singleton
# ---------------------------------------------------------------------------

_extractor: IntentExtractor | None = None
_lock = threading.Lock()


def get_extractor() -> IntentExtractor:
    """Return the (optionally compiled) IntentExtractor singleton.

    - If compiled_intent.json exists next to this file, load it (includes
      bootstrapped few-shot demonstrations discovered by the optimizer).
    - Otherwise fall back to zero-shot with the typed signature above.
    """
    global _extractor
    if _extractor is None:
        with _lock:
            if _extractor is None:
                _configure_dspy()
                e = IntentExtractor()
                if _COMPILED_PATH.exists():
                    e.load(str(_COMPILED_PATH))
                _extractor = e
    return _extractor
