"""Tests for the NL→SQL builder — deterministic, no LLM required."""
from __future__ import annotations

import pytest

from app.nl_query.intent import Filter, OrderBy, QueryIntent
from app.nl_query.sql_builder import build_sql

WS = "ws-test"


def sql(intent: QueryIntent) -> str:
    s, _ = build_sql(intent, workspace_id=WS)
    return " ".join(s.split())  # normalise whitespace


def params(intent: QueryIntent) -> dict:
    _, p = build_sql(intent, workspace_id=WS)
    return p


# ---------------------------------------------------------------------------
# Workspace scoping
# ---------------------------------------------------------------------------

class TestWorkspaceScoping:

    def test_document_is_workspace_scoped(self):
        q = QueryIntent(table="document")
        assert "workspace_id = :_workspace_id" in sql(q)
        assert params(q)["_workspace_id"] == WS

    def test_document_chunk_is_workspace_scoped(self):
        q = QueryIntent(table="document_chunk")
        assert "workspace_id = :_workspace_id" in sql(q)

    def test_trace_log_is_workspace_scoped(self):
        q = QueryIntent(table="trace_log")
        assert "workspace_id = :_workspace_id" in sql(q)

    def test_ingestion_run_is_not_workspace_scoped(self):
        q = QueryIntent(table="ingestion_run")
        assert "workspace_id" not in sql(q)


# ---------------------------------------------------------------------------
# SELECT clause
# ---------------------------------------------------------------------------

class TestSelectClause:

    def test_empty_select_columns_expands_to_all(self):
        q = QueryIntent(table="document", select_columns=[])
        s = sql(q)
        for col in ("id", "workspace_id", "source_name", "title", "text", "created_at"):
            assert col in s

    def test_explicit_select_columns(self):
        q = QueryIntent(table="document", select_columns=["id", "title"])
        s = sql(q)
        assert "SELECT id, title" in s

    def test_count_star_when_no_aggregation_column(self):
        q = QueryIntent(table="document", aggregation="COUNT")
        assert "COUNT(*)" in sql(q)

    def test_count_with_column(self):
        q = QueryIntent(table="trace_log", aggregation="COUNT", aggregation_column="latency_ms")
        assert "COUNT(latency_ms)" in sql(q)

    def test_avg_aggregation(self):
        q = QueryIntent(table="trace_log", aggregation="AVG", aggregation_column="latency_ms")
        assert "AVG(latency_ms)" in sql(q)

    def test_max_aggregation(self):
        q = QueryIntent(table="trace_log", aggregation="MAX", aggregation_column="latency_ms")
        assert "MAX(latency_ms)" in sql(q)

    def test_group_by_prepended_to_agg_expr(self):
        q = QueryIntent(table="document", aggregation="COUNT", group_by=["source_name"])
        s = sql(q)
        assert "source_name, COUNT(*)" in s
        assert "GROUP BY source_name" in s


# ---------------------------------------------------------------------------
# WHERE clause / filters
# ---------------------------------------------------------------------------

class TestFilters:

    def test_equality_filter(self):
        q = QueryIntent(
            table="ingestion_run",
            filters=[Filter(column="status", operator="=", value="failed")],
        )
        s, p = build_sql(q, workspace_id=WS)
        assert "status = :_v0" in s
        assert p["_v0"] == "failed"

    def test_ilike_filter(self):
        q = QueryIntent(
            table="document",
            filters=[Filter(column="title", operator="ILIKE", value="%report%")],
        )
        s, p = build_sql(q, workspace_id=WS)
        assert "title ILIKE :_v0" in s
        assert p["_v0"] == "%report%"

    def test_gt_filter(self):
        q = QueryIntent(
            table="trace_log",
            filters=[Filter(column="latency_ms", operator=">", value=1000)],
        )
        s, p = build_sql(q, workspace_id=WS)
        assert "latency_ms > :_v0" in s
        assert p["_v0"] == 1000

    def test_is_null_filter(self):
        q = QueryIntent(
            table="ingestion_run",
            filters=[Filter(column="error", operator="IS NULL")],
        )
        s = sql(q)
        assert "error IS NULL" in s

    def test_is_not_null_filter(self):
        q = QueryIntent(
            table="ingestion_run",
            filters=[Filter(column="error", operator="IS NOT NULL")],
        )
        s = sql(q)
        assert "error IS NOT NULL" in s

    def test_in_filter(self):
        q = QueryIntent(
            table="ingestion_run",
            filters=[Filter(column="status", operator="IN", value=["failed", "pending"])],
        )
        s, p = build_sql(q, workspace_id=WS)
        assert "status IN" in s
        assert p["_v0_0"] == "failed"
        assert p["_v0_1"] == "pending"

    def test_multiple_filters_joined_with_and(self):
        q = QueryIntent(
            table="trace_log",
            filters=[
                Filter(column="trace_type", operator="=", value="generation"),
                Filter(column="latency_ms", operator=">", value=500),
            ],
        )
        s = sql(q)
        assert "AND" in s
        assert "trace_type = :_v0" in s
        assert "latency_ms > :_v1" in s

    def test_workspace_and_filter_combined(self):
        q = QueryIntent(
            table="document",
            filters=[Filter(column="source_name", operator="=", value="upload")],
        )
        s = sql(q)
        assert "workspace_id = :_workspace_id" in s
        assert "source_name = :_v0" in s


# ---------------------------------------------------------------------------
# ORDER BY / LIMIT
# ---------------------------------------------------------------------------

class TestOrderByLimit:

    def test_order_by_desc(self):
        q = QueryIntent(table="document", order_by=OrderBy(column="created_at", direction="DESC"))
        assert "ORDER BY created_at DESC" in sql(q)

    def test_order_by_asc(self):
        q = QueryIntent(table="trace_log", order_by=OrderBy(column="latency_ms", direction="ASC"))
        assert "ORDER BY latency_ms ASC" in sql(q)

    def test_limit_applied(self):
        q = QueryIntent(table="document", limit=25)
        assert "LIMIT 25" in sql(q)

    def test_limit_capped_at_1000(self):
        # QueryIntent validator caps at 1000, but build_sql also enforces it
        q = QueryIntent(table="document", limit=1000)
        assert "LIMIT 1000" in sql(q)

    def test_default_limit_100(self):
        q = QueryIntent(table="document")
        assert "LIMIT 100" in sql(q)


# ---------------------------------------------------------------------------
# Full query shapes
# ---------------------------------------------------------------------------

class TestFullQueries:

    def test_count_all_documents(self):
        q = QueryIntent(table="document", aggregation="COUNT")
        s = sql(q)
        assert s == (
            "SELECT COUNT(*) FROM document "
            "WHERE workspace_id = :_workspace_id LIMIT 100"
        )

    def test_failed_ingestion_runs(self):
        q = QueryIntent(
            table="ingestion_run",
            filters=[Filter(column="status", operator="=", value="failed")],
        )
        s = sql(q)
        assert "FROM ingestion_run" in s
        assert "status = :_v0" in s
        assert "workspace_id" not in s   # not scoped

    def test_slowest_traces(self):
        q = QueryIntent(
            table="trace_log",
            order_by=OrderBy(column="latency_ms", direction="DESC"),
            limit=5,
        )
        s = sql(q)
        assert "FROM trace_log" in s
        assert "ORDER BY latency_ms DESC" in s
        assert "LIMIT 5" in s

    def test_avg_latency_per_trace_type(self):
        q = QueryIntent(
            table="trace_log",
            aggregation="AVG",
            aggregation_column="latency_ms",
            group_by=["trace_type"],
        )
        s = sql(q)
        assert "trace_type, AVG(latency_ms)" in s
        assert "GROUP BY trace_type" in s
