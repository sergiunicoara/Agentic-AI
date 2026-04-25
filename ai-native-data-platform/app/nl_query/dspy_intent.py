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
# Normalization maps — applied before Pydantic validation
# The LLM often uses plural, abbreviated, or natural-language variants.
# ---------------------------------------------------------------------------

_TABLE_ALIASES: dict[str, str] = {
    "documents": "document",
    "document_chunks": "document_chunk",
    "chunks": "document_chunk",
    "chunk": "document_chunk",
    "indexed_chunks": "document_chunk",
    "ingestion_runs": "ingestion_run",
    "ingestion": "ingestion_run",
    "runs": "ingestion_run",
    "traces": "trace_log",
    "trace_logs": "trace_log",
    "trace": "trace_log",
    "logs": "trace_log",
    "generation_traces": "trace_log",
    "generation_trace": "trace_log",
    "latency_records": "trace_log",
    "request_logs": "trace_log",
}

_OPERATOR_ALIASES: dict[str, str] = {
    "contains": "ILIKE",
    "ilike": "ILIKE",
    "like": "ILIKE",           # normalise to ILIKE for case-insensitive search
    "equals": "=",
    "eq": "=",
    "not equals": "!=",
    "ne": "!=",
    "greater than": ">",
    "gt": ">",
    "less than": "<",
    "lt": "<",
    "gte": ">=",
    "lte": "<=",
    "is null": "IS NULL",
    "isnull": "IS NULL",
    "is not null": "IS NOT NULL",
    "isnotnull": "IS NOT NULL",
    "in": "IN",
}

# Per-table column aliases — maps LLM hallucinations to real column names.
_COLUMN_ALIASES: dict[str, dict[str, str]] = {
    "document": {
        "source": "source_name",
        "timestamp": "created_at",
        "ingest_timestamp": "created_at",
        "ingest_time": "created_at",
        "ingested_at": "created_at",
        "doc_id": "id",
    },
    "document_chunk": {
        "chunk_id": "id",
        "text": "chunk_text",
        "content": "chunk_text",
        "hash": "chunk_hash",
        "index": "chunk_index",
        "timestamp": "created_at",
        "ingested_at": "created_at",
        "version": "embedding_version",
    },
    "ingestion_run": {
        "run_id": "id",
        "ingestion_time": "created_at",
        "start_time": "created_at",
        "timestamp": "created_at",
        "ingested_at": "created_at",
        "finish_time": "finished_at",
        "completed_at": "finished_at",
        "error_message": "error",
        "err": "error",
        "message": "error",
    },
    "trace_log": {
        "latency": "latency_ms",
        "duration": "latency_ms",
        "duration_ms": "latency_ms",
        "response_time": "latency_ms",
        "elapsed_ms": "latency_ms",
        "timestamp": "created_at",
        "created": "created_at",
        "type": "trace_type",
        "log_type": "trace_type",
        "log_id": "id",
        "trace_id": "id",
    },
}


def _fix_col(col: str, col_map: dict[str, str]) -> str:
    return col_map.get(str(col).strip().lower(), col)


def _normalize_data(data: dict) -> dict:
    """Coerce LLM output to the exact values Pydantic / build_sql expect."""

    # ── Table name ────────────────────────────────────────────────────────────
    table = str(data.get("table", "")).strip().lower()
    table = _TABLE_ALIASES.get(table, table)
    data["table"] = table

    col_map = _COLUMN_ALIASES.get(table, {})
    allowed = set(ALLOWED_SCHEMA.get(table, []))

    # ── limit: null → 100 ─────────────────────────────────────────────────────
    if data.get("limit") is None:
        data["limit"] = 100

    # ── select_columns: ["*"] → [] so build_sql expands to all columns ────────
    sc = data.get("select_columns") or []
    if isinstance(sc, list):
        if sc in (["*"], ["all"], ["ALL"]):
            sc = []
        else:
            sc = [_fix_col(c, col_map) for c in sc]
            sc = [c for c in sc if c in allowed]   # drop hallucinated columns
    data["select_columns"] = sc

    # ── aggregation_column: alias + COUNT(*) normalisation ────────────────────
    agg = str(data.get("aggregation") or "").upper()
    agg_col = data.get("aggregation_column")
    if agg_col:
        agg_col = _fix_col(str(agg_col), col_map)
        # COUNT(id) / COUNT(*) / COUNT(1) → COUNT(*) by setting agg_col=null
        if agg == "COUNT" and agg_col in ("id", "*", "1", "all"):
            agg_col = None
        elif agg_col not in allowed:
            agg_col = None          # drop hallucinated column
        data["aggregation_column"] = agg_col
    elif agg == "COUNT":
        data["aggregation_column"] = None   # ensure COUNT(*)

    # ── group_by: alias + filter ───────────────────────────────────────────────
    gb = data.get("group_by") or []
    if isinstance(gb, list):
        gb = [_fix_col(c, col_map) for c in gb]
        gb = [c for c in gb if c in allowed]
    data["group_by"] = gb

    # ── order_by: alias column, drop if still invalid ─────────────────────────
    ob = data.get("order_by")
    if ob and isinstance(ob, dict) and "column" in ob:
        col = _fix_col(str(ob["column"]), col_map)
        if col in allowed:
            ob["column"] = col
        else:
            data["order_by"] = None

    # ── filters: operator alias + column alias + ILIKE wildcard ──────────────
    for f in data.get("filters") or []:
        if not isinstance(f, dict):
            continue
        if "column" in f:
            f["column"] = _fix_col(str(f["column"]), col_map)
        raw_op = str(f.get("operator", "")).strip().lower()
        f["operator"] = _OPERATOR_ALIASES.get(raw_op, f.get("operator", "="))
        if raw_op in ("contains", "like", "ilike") and isinstance(f.get("value"), str):
            v = f["value"]
            if not v.startswith("%"):
                f["value"] = f"%{v}%"

    return data


# ---------------------------------------------------------------------------
# DSPy Module
# ---------------------------------------------------------------------------


class IntentExtractor(dspy.Module):
    """ChainOfThought extractor — reasoning step improves structured accuracy."""

    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.ChainOfThought(NLToIntent)

    def forward(self, nl_query: str) -> dspy.Prediction:  # type: ignore[override]
        result = self.predict(nl_query=nl_query)
        raw = result.intent_json.strip()
        # Strip accidental markdown fences the LLM sometimes emits.
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = _normalize_data(json.loads(raw.strip()))
        intent = QueryIntent.model_validate(data)
        # Return a Prediction so the metric can access both the raw JSON
        # (for debugging) and the validated intent object.
        return dspy.Prediction(intent_json=result.intent_json, intent=intent)


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
