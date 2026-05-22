"""
CCA-F D4.3: Structured Output — JSON schema + Pydantic enforcement
The canonical output schema for the system. Tool use with JSON schemas is the
most reliable approach for schema-compliant output (exam fact — D4.3).
"""
from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator


class SeverityLevel(str, Enum):
    P1 = "P1"   # Complete outage or data loss risk
    P2 = "P2"   # Significant degradation or security vulnerability
    P3 = "P3"   # Minor degradation, workaround exists
    P4 = "P4"   # Cosmetic, no user impact


class EvidenceItem(BaseModel):
    fact: str = Field(..., description="Specific, verifiable fact — not an interpretation")
    source: str = Field(..., description="Data source name: prometheus, app_logs, runbook, etc.")
    ts: str = Field(default="", description="ISO 8601 timestamp when this fact was true")
    url: str = Field(default="", description="Direct link to source if available")


class RCAOutput(BaseModel):
    """
    D4.3: The enforced output schema for all RCA reports.
    Every field has explicit description — this IS the prompt for the output structure.
    """
    ticket_id: str = Field(..., description="The incident/ticket identifier")
    root_cause: str = Field(
        ...,
        description="Precise root cause statement. Must name the specific component, "
                    "operation, and failure mode. No vague language.",
        min_length=20,
    )
    severity: SeverityLevel = Field(
        ...,
        description="P1=outage/data loss, P2=degradation/security, P3=minor, P4=cosmetic"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Calibrated confidence in this RCA. <0.65 triggers escalation.",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="All facts used to reach this conclusion, each with source attribution",
    )
    next_steps: list[str] = Field(
        ...,
        description="Specific, actionable remediation steps. No generic steps like 'investigate'.",
        min_length=1,
    )
    escalate: bool = Field(
        default=False,
        description="True if human review is required",
    )
    escalation_reason: str | None = Field(
        default=None,
        description="Required when escalate=True. Specific reason for escalation.",
    )
    provenance: dict | None = Field(
        default=None,
        description="Source attribution map from ProvenanceTracker.get_provenance_map()",
    )
    coverage: dict | None = Field(
        default=None,
        description="Coverage annotation — which agents ran, which were skipped (D5.3)",
    )

    @field_validator("escalation_reason")
    @classmethod
    def escalation_reason_required_when_escalating(cls, v, info):
        if info.data.get("escalate") and not v:
            raise ValueError("escalation_reason is required when escalate=True")
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_triggers_escalation_check(cls, v, info):
        # Validator doesn't set escalate — that's done by EscalationManager
        # But we log for awareness
        if v < 0.65:
            import logging
            logging.getLogger(__name__).info(f"Low confidence {v:.2f} — EscalationManager will flag")
        return v

    def to_api_response(self) -> dict:
        """Clean serialization for API responses."""
        return self.model_dump(exclude_none=True, mode="json")


class AgentError(BaseModel):
    """
    D5.3 + D2.2: Structured error for agent-to-agent and MCP error propagation.
    NEVER use raw exceptions across agent boundaries.
    """
    error_type: str = Field(
        ...,
        description="One of: timeout, validation, permission, business_rule, "
                    "max_iterations, runtime, access_error",
    )
    source: str = Field(..., description="Agent or MCP server that produced this error")
    recoverable: bool = Field(
        ...,
        description="True = retry or fallback is possible. False = escalate.",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context: attempted action, fallback tried, etc.",
    )
    message: str = Field(default="", description="Human-readable error message")
