"""Tests for _normalize_data — the LLM output coercion layer in dspy_intent."""
from __future__ import annotations

import pytest

from app.nl_query.dspy_intent import _normalize_data


def norm(data: dict) -> dict:
    """Helper: clone + normalize."""
    import copy
    return _normalize_data(copy.deepcopy(data))


# ---------------------------------------------------------------------------
# Table aliases
# ---------------------------------------------------------------------------

class TestTableAliases:

    @pytest.mark.parametrize("alias,expected", [
        ("documents", "document"),
        ("document_chunks", "document_chunk"),
        ("chunks", "document_chunk"),
        ("chunk", "document_chunk"),
        ("indexed_chunks", "document_chunk"),
        ("ingestion_runs", "ingestion_run"),
        ("ingestion", "ingestion_run"),
        ("runs", "ingestion_run"),
        ("traces", "trace_log"),
        ("trace_logs", "trace_log"),
        ("trace", "trace_log"),
        ("logs", "trace_log"),
        ("generation_traces", "trace_log"),
        ("latency_records", "trace_log"),
    ])
    def test_table_alias_resolved(self, alias, expected):
        result = norm({"table": alias, "limit": 100})
        assert result["table"] == expected

    def test_canonical_table_unchanged(self):
        for t in ("document", "document_chunk", "ingestion_run", "trace_log"):
            result = norm({"table": t, "limit": 100})
            assert result["table"] == t


# ---------------------------------------------------------------------------
# limit coercion
# ---------------------------------------------------------------------------

class TestLimitCoercion:

    def test_null_limit_becomes_100(self):
        result = norm({"table": "document", "limit": None})
        assert result["limit"] == 100

    def test_explicit_limit_preserved(self):
        result = norm({"table": "document", "limit": 10})
        assert result["limit"] == 10

    def test_limit_1000_preserved(self):
        result = norm({"table": "document", "limit": 1000})
        assert result["limit"] == 1000


# ---------------------------------------------------------------------------
# select_columns
# ---------------------------------------------------------------------------

class TestSelectColumns:

    def test_star_list_becomes_empty(self):
        result = norm({"table": "document", "limit": 100, "select_columns": ["*"]})
        assert result["select_columns"] == []

    def test_all_list_becomes_empty(self):
        result = norm({"table": "document", "limit": 100, "select_columns": ["all"]})
        assert result["select_columns"] == []

    def test_empty_list_unchanged(self):
        result = norm({"table": "document", "limit": 100, "select_columns": []})
        assert result["select_columns"] == []

    def test_valid_columns_preserved(self):
        result = norm({"table": "document", "limit": 100, "select_columns": ["id", "title"]})
        assert result["select_columns"] == ["id", "title"]

    def test_hallucinated_columns_dropped(self):
        result = norm({"table": "document", "limit": 100, "select_columns": ["id", "nonexistent_col"]})
        assert result["select_columns"] == ["id"]

    def test_column_alias_applied(self):
        # "source" → "source_name" for document table
        result = norm({"table": "document", "limit": 100, "select_columns": ["id", "source"]})
        assert "source_name" in result["select_columns"]
        assert "source" not in result["select_columns"]


# ---------------------------------------------------------------------------
# COUNT(*) normalisation
# ---------------------------------------------------------------------------

class TestCountNormalisation:

    def test_count_with_id_column_becomes_star(self):
        result = norm({
            "table": "document",
            "limit": 100,
            "aggregation": "COUNT",
            "aggregation_column": "id",
        })
        assert result["aggregation_column"] is None

    def test_count_with_star_string_becomes_none(self):
        result = norm({
            "table": "document",
            "limit": 100,
            "aggregation": "COUNT",
            "aggregation_column": "*",
        })
        assert result["aggregation_column"] is None

    def test_count_without_column_stays_none(self):
        result = norm({
            "table": "document",
            "limit": 100,
            "aggregation": "COUNT",
            "aggregation_column": None,
        })
        assert result["aggregation_column"] is None

    def test_avg_with_valid_column_preserved(self):
        result = norm({
            "table": "trace_log",
            "limit": 100,
            "aggregation": "AVG",
            "aggregation_column": "latency_ms",
        })
        assert result["aggregation_column"] == "latency_ms"

    def test_avg_with_aliased_column_normalized(self):
        # "latency" → "latency_ms" on trace_log
        result = norm({
            "table": "trace_log",
            "limit": 100,
            "aggregation": "AVG",
            "aggregation_column": "latency",
        })
        assert result["aggregation_column"] == "latency_ms"

    def test_avg_with_hallucinated_column_dropped(self):
        result = norm({
            "table": "trace_log",
            "limit": 100,
            "aggregation": "AVG",
            "aggregation_column": "nonexistent",
        })
        assert result["aggregation_column"] is None


# ---------------------------------------------------------------------------
# Column aliases — filters, group_by, order_by
# ---------------------------------------------------------------------------

class TestColumnAliases:

    def test_filter_column_alias_applied(self):
        # "latency" → "latency_ms" on trace_log
        result = norm({
            "table": "trace_log",
            "limit": 100,
            "filters": [{"column": "latency", "operator": "=", "value": 500}],
        })
        assert result["filters"][0]["column"] == "latency_ms"

    def test_filter_column_source_alias(self):
        # "source" → "source_name" on document
        result = norm({
            "table": "document",
            "limit": 100,
            "filters": [{"column": "source", "operator": "=", "value": "upload"}],
        })
        assert result["filters"][0]["column"] == "source_name"

    def test_order_by_alias_applied(self):
        # "duration" → "latency_ms" on trace_log
        result = norm({
            "table": "trace_log",
            "limit": 5,
            "order_by": {"column": "duration", "direction": "DESC"},
        })
        assert result["order_by"]["column"] == "latency_ms"

    def test_order_by_hallucinated_column_dropped(self):
        result = norm({
            "table": "trace_log",
            "limit": 5,
            "order_by": {"column": "nonexistent_field", "direction": "DESC"},
        })
        assert result["order_by"] is None

    def test_group_by_alias_applied(self):
        result = norm({
            "table": "trace_log",
            "limit": 100,
            "aggregation": "COUNT",
            "group_by": ["type"],   # "type" → "trace_type"
        })
        assert "trace_type" in result["group_by"]

    def test_group_by_hallucinated_column_dropped(self):
        result = norm({
            "table": "document",
            "limit": 100,
            "group_by": ["nonexistent"],
        })
        assert result["group_by"] == []


# ---------------------------------------------------------------------------
# Operator aliases
# ---------------------------------------------------------------------------

class TestOperatorAliases:

    @pytest.mark.parametrize("raw,expected", [
        ("contains", "ILIKE"),
        ("like", "ILIKE"),
        ("ilike", "ILIKE"),
        ("equals", "="),
        ("eq", "="),
        ("not equals", "!="),
        ("greater than", ">"),
        ("gt", ">"),
        ("less than", "<"),
        ("lt", "<"),
        ("is null", "IS NULL"),
        ("is not null", "IS NOT NULL"),
    ])
    def test_operator_alias_normalised(self, raw, expected):
        result = norm({
            "table": "document",
            "limit": 100,
            "filters": [{"column": "title", "operator": raw, "value": "test"}],
        })
        assert result["filters"][0]["operator"] == expected

    def test_contains_wraps_value_with_percent(self):
        result = norm({
            "table": "document",
            "limit": 100,
            "filters": [{"column": "title", "operator": "contains", "value": "report"}],
        })
        assert result["filters"][0]["value"] == "%report%"

    def test_ilike_wraps_value_if_missing_percent(self):
        result = norm({
            "table": "document",
            "limit": 100,
            "filters": [{"column": "title", "operator": "ilike", "value": "report"}],
        })
        assert result["filters"][0]["value"] == "%report%"

    def test_already_wrapped_value_not_double_wrapped(self):
        result = norm({
            "table": "document",
            "limit": 100,
            "filters": [{"column": "title", "operator": "contains", "value": "%report%"}],
        })
        assert result["filters"][0]["value"] == "%report%"

    def test_unknown_operator_passed_through(self):
        result = norm({
            "table": "document",
            "limit": 100,
            "filters": [{"column": "title", "operator": "=", "value": "x"}],
        })
        assert result["filters"][0]["operator"] == "="


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:

    def test_normalize_is_idempotent(self):
        data = {
            "table": "trace_log",
            "limit": 100,
            "aggregation": "AVG",
            "aggregation_column": "latency_ms",
            "group_by": ["trace_type"],
            "order_by": {"column": "latency_ms", "direction": "DESC"},
            "filters": [{"column": "latency_ms", "operator": "ILIKE", "value": "%gen%"}],
            "select_columns": [],
        }
        import copy
        first = _normalize_data(copy.deepcopy(data))
        second = _normalize_data(copy.deepcopy(first))
        assert first == second
