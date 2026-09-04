"""Regression tests for app.nl_query.validator's aggregation whitelist.

`QueryIntent.aggregation` is interpolated as a raw SQL keyword (not a bound
parameter — it can't be, SQL doesn't allow parameterizing a keyword) directly
into the SELECT clause by build_sql(). Before this fix, validate_intent()
whitelisted every other field on QueryIntent (table, columns, filters,
group_by, order_by, aggregation_column) but never checked `aggregation`
itself, so a crafted or LLM-hallucinated value there was a straight SQL
injection into a query that otherwise looks fully parameterized.
"""
from __future__ import annotations

from app.nl_query.intent import QueryIntent
from app.nl_query.validator import validate_intent


class TestAggregationWhitelist:

    def test_known_aggregations_are_allowed(self):
        for agg in ("COUNT", "SUM", "AVG", "MIN", "MAX"):
            q = QueryIntent(table="document", aggregation=agg)
            result = validate_intent(q)
            assert result.ok, f"{agg} should be allowed, got error: {result.error}"

    def test_lowercase_known_aggregation_is_allowed(self):
        q = QueryIntent(table="document", aggregation="count")
        assert validate_intent(q).ok

    def test_none_aggregation_is_allowed(self):
        q = QueryIntent(table="document", aggregation=None)
        assert validate_intent(q).ok

    def test_injection_payload_is_rejected(self):
        # Attempts to break out of the SELECT clause and read another table
        # entirely (e.g. workspace_api_key, which has no RLS policy).
        malicious = "* FROM workspace_api_key --"
        q = QueryIntent(table="document", aggregation=malicious)
        result = validate_intent(q)
        assert not result.ok
        assert "aggregation" in result.error.lower() or "Aggregation" in result.error

    def test_unknown_function_name_is_rejected(self):
        q = QueryIntent(table="document", aggregation="STRING_AGG")
        result = validate_intent(q)
        assert not result.ok


class TestAggregationWhitelistDefenseInDepth:
    """build_sql() must independently reject an unsafe aggregation too —
    it must never assume validate_intent() was called first."""

    def test_build_sql_rejects_malicious_aggregation_even_without_validation(self):
        import pytest

        from app.nl_query.sql_builder import build_sql

        malicious = "* FROM workspace_api_key --"
        q = QueryIntent(table="document", aggregation=malicious)
        with pytest.raises(ValueError):
            build_sql(q, workspace_id="ws-test")
