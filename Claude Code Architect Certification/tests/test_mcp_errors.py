"""Tests for MCP structured error responses — D2.2."""
import json
import pytest
from mcp.errors import transient_error, validation_error, permission_error, business_error


class TestMCPErrors:
    def test_transient_error_is_recoverable(self):
        result = transient_error("Connection timeout", source="postgres_server", retry_after=5)
        assert result["isError"] is True
        payload = json.loads(result["content"][0]["text"])
        assert payload["error_type"] == "transient"
        assert payload["recoverable"] is True
        assert payload["retry_after"] == 5

    def test_validation_error_not_recoverable(self):
        result = validation_error("Bad input", source="fs_server", expected_format="INC-XXXX")
        payload = json.loads(result["content"][0]["text"])
        assert payload["error_type"] == "validation"
        assert payload["recoverable"] is False
        assert "expected_format" in payload

    def test_permission_error_triggers_escalation(self):
        result = permission_error("Access denied", source="postgres_server")
        payload = json.loads(result["content"][0]["text"])
        assert payload["error_type"] == "permission"
        assert payload["recoverable"] is False
        assert payload["escalate"] is True

    def test_business_error_triggers_escalation(self):
        result = business_error("Policy violation", source="incident_server")
        payload = json.loads(result["content"][0]["text"])
        assert payload["escalate"] is True

    def test_error_always_has_source(self):
        """Every MCP error must identify its source — D2.2."""
        for fn, kwargs in [
            (transient_error, {"message": "err", "source": "test_srv"}),
            (validation_error, {"message": "err", "source": "test_srv", "expected_format": "x"}),
            (permission_error, {"message": "err", "source": "test_srv"}),
        ]:
            result = fn(**kwargs)
            payload = json.loads(result["content"][0]["text"])
            assert payload.get("source"), f"{fn.__name__} missing source"
