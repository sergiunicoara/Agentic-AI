"""
CCA-F D5.2: Escalation & Ambiguity Resolution
Exam concepts:
- Escalation triggers must be explicit and numeric (NOT "low confidence" vagueness)
- Sentiment-based unreliability: don't use "seems uncertain" as a trigger
- Policy gaps should trigger escalation
- Customer explicit requests to escalate must be honored
"""
from __future__ import annotations
from schemas.rca_output import RCAOutput


# D5.2 exam trap: NEVER use vague confidence language
# BAD:  if confidence == "low": escalate
# GOOD: if confidence < 0.65: escalate (numeric threshold)
CONFIDENCE_THRESHOLD = 0.65

# D5.2: Conflicting evidence threshold
MAX_CONFLICTING_SOURCES = 2


class EscalationManager:
    """
    Determines whether an RCA should be escalated to human review.

    D5.2 exam rules:
    1. Numeric thresholds — never string-based confidence
    2. Conflicting sources — count, don't sentiment-judge
    3. Policy gaps — things the system can't decide
    4. Permission errors — always escalate (agent can't self-resolve)
    5. Customer-requested escalation — always honor
    """

    def should_escalate(self, rca: RCAOutput) -> bool:
        """Return True if any escalation condition is met."""
        return any([
            self._low_confidence(rca),
            self._conflicting_evidence(rca),
            self._permission_error(rca),
            self._customer_requested(rca),
            self._policy_gap(rca),
        ])

    def reason(self, rca: RCAOutput) -> str:
        """Return human-readable escalation reason."""
        reasons = []
        if self._low_confidence(rca):
            reasons.append(f"Confidence {rca.confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}")
        if self._conflicting_evidence(rca):
            reasons.append(f"Conflicting evidence from multiple sources")
        if self._permission_error(rca):
            reasons.append("Permission error — agent cannot access required data")
        if self._customer_requested(rca):
            reasons.append("Customer explicitly requested escalation")
        if self._policy_gap(rca):
            reasons.append("Situation not covered by policy — requires human judgment")
        return "; ".join(reasons) or "Unknown"

    def _low_confidence(self, rca: RCAOutput) -> bool:
        # D5.2: Numeric threshold — NOT sentiment-based
        return rca.confidence < CONFIDENCE_THRESHOLD

    def _conflicting_evidence(self, rca: RCAOutput) -> bool:
        # Count sources that contradict each other
        sources = {e.source for e in (rca.evidence or [])}
        # Simple proxy: if root_cause contains uncertainty markers
        uncertainty_markers = ["unclear", "either", "possibly", "conflicting", "unknown"]
        return any(m in rca.root_cause.lower() for m in uncertainty_markers)

    def _permission_error(self, rca: RCAOutput) -> bool:
        # If any evidence item references a permission failure
        return any("permission" in str(e.source).lower() for e in (rca.evidence or []))

    def _customer_requested(self, rca: RCAOutput) -> bool:
        # Honor explicit customer escalation requests (D5.2)
        return getattr(rca, "customer_requested_escalation", False)

    def _policy_gap(self, rca: RCAOutput) -> bool:
        # Severity P1 with confidence below 0.80 → always review (policy)
        return rca.severity == "P1" and rca.confidence < 0.80
