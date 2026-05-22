"""Tests for structured output and validation — D4.3 + D4.4."""
import pytest
from pydantic import ValidationError
from schemas.rca_output import RCAOutput, AgentError, SeverityLevel
from agents.validator import _classify_error, _semantic_validate, _build_retry_feedback


class TestRCAOutputSchema:
    def test_valid_rca(self):
        rca = RCAOutput(
            ticket_id="INC-001",
            root_cause="PostgreSQL connection pool exhausted due to slow queries",
            severity=SeverityLevel.P1,
            confidence=0.91,
            evidence=[{"fact": "CPU 98%", "source": "prometheus"}],
            next_steps=["Increase pool size"],
            escalate=False,
        )
        assert rca.severity == SeverityLevel.P1
        assert rca.confidence == 0.91

    def test_escalation_requires_reason(self):
        with pytest.raises(ValidationError, match="escalation_reason"):
            RCAOutput(
                ticket_id="INC-001",
                root_cause="Unknown failure in payment service component",
                severity=SeverityLevel.P2,
                confidence=0.40,
                next_steps=["Investigate"],
                escalate=True,
                # escalation_reason missing — should fail
            )

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            RCAOutput(
                ticket_id="INC-001",
                root_cause="Something broke in the main service component",
                severity=SeverityLevel.P3,
                confidence=1.5,  # out of bounds
                next_steps=["Fix it"],
                escalate=False,
            )

    def test_root_cause_min_length(self):
        with pytest.raises(ValidationError):
            RCAOutput(
                ticket_id="INC-001",
                root_cause="short",  # too short
                severity=SeverityLevel.P3,
                confidence=0.7,
                next_steps=["Fix"],
                escalate=False,
            )


class TestSemanticValidation:
    def test_zero_confidence_with_root_cause(self):
        rca = RCAOutput(
            ticket_id="t1",
            root_cause="Database connection pool was completely exhausted",
            severity=SeverityLevel.P1,
            confidence=0.0,
            next_steps=["Check connections"],
            escalate=True,
            escalation_reason="low confidence"
        )
        errors = _semantic_validate(rca)
        assert any("0.0" in e or "not calibrated" in e for e in errors)

    def test_p1_without_evidence(self):
        rca = RCAOutput(
            ticket_id="t1",
            root_cause="Critical database failure in primary connection pool",
            severity=SeverityLevel.P1,
            confidence=0.9,
            evidence=[],  # P1 needs evidence
            next_steps=["Fix the database"],
            escalate=False,
        )
        errors = _semantic_validate(rca)
        assert any("evidence" in e.lower() for e in errors)


class TestErrorClassification:
    def test_classify_missing_field(self):
        assert _classify_error("field required") == "schema_missing_field"

    def test_classify_information_absence(self):
        assert _classify_error("value is not found") == "information_absence"

    def test_retry_feedback_format(self):
        fb = _build_retry_feedback("schema_missing_field", "field 'confidence' is required", 1)
        assert "Missing required field" in fb
        assert "confidence" in fb


class TestAgentError:
    def test_agent_error_model(self):
        err = AgentError(
            error_type="timeout",
            source="retrieval_agent",
            recoverable=True,
            context={"attempted": "search_kb", "retry_after": 5},
        )
        d = err.model_dump()
        assert d["error_type"] == "timeout"
        assert d["recoverable"] is True
