"""
CCA-F D4.1 + D4.2 + D4.3 + D4.6: Report Generator Subagent
Combines: explicit criteria, few-shot prompting, structured output via tool_choice,
and the multi-instance review pattern.
"""
from __future__ import annotations
import json
import logging
import anthropic
from schemas.rca_output import RCAOutput, SeverityLevel, EvidenceItem

logger = logging.getLogger(__name__)

# D4.2: Few-shot examples embedded in system prompt
# These are the MOST effective technique for consistent formatted output (exam fact)
FEW_SHOT_EXAMPLES = """
## Output Examples (follow these exactly)

### Example 1: Database connection pool exhaustion
Input evidence: logs show "connection timeout" at 14:32, DB CPU 98%, alert fired at 14:30
Output:
{
  "root_cause": "PostgreSQL connection pool exhausted due to slow queries holding connections beyond pool timeout",
  "severity": "P1",
  "confidence": 0.91,
  "evidence": [
    {"fact": "DB CPU reached 98% at 14:30", "source": "prometheus", "ts": "2026-05-21T14:30:00Z"},
    {"fact": "Connection timeout errors in app logs at 14:32", "source": "application_logs", "ts": "2026-05-21T14:32:00Z"}
  ],
  "next_steps": ["Increase connection pool size", "Add query timeout", "Review slow query log"],
  "escalate": false
}

### Example 2: Ambiguous root cause (triggers escalation)
Input evidence: partial logs, conflicting metrics
Output:
{
  "root_cause": "Unclear — either memory leak in worker process or OOM kill by kernel",
  "severity": "P2",
  "confidence": 0.48,
  "evidence": [...],
  "next_steps": ["Collect heap dump", "Review kernel OOM logs"],
  "escalate": true,
  "escalation_reason": "Confidence 0.48 below threshold 0.65; conflicting evidence requires human review"
}
"""

# D4.1: Explicit criteria — NOT vague ("be accurate") but specific categories
SEVERITY_CRITERIA = """
## Severity Criteria (use ONLY these definitions — no interpretation)
P1: Complete service outage affecting >10% users OR data loss risk
P2: Significant degradation affecting >1% users OR security vulnerability
P3: Minor degradation, <1% users affected, workaround exists
P4: Cosmetic issue, no user impact

## Confidence Calibration (numeric thresholds, not vague descriptions)
>= 0.85: High confidence — direct evidence available
0.65-0.84: Medium confidence — strong correlation, some gaps
< 0.65: Low confidence — escalate to human review (REQUIRED)
"""


class ReportGeneratorAgent:
    """
    Synthesizes findings from all subagents into a structured RCA report.
    Uses multi-instance review (D4.6) to catch self-review blind spots.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()

    async def run(self, context: dict) -> RCAOutput:
        """
        context must contain (explicit — D1.3):
        - dependency_results: dict with retrieval, log_analysis, code_analysis outputs
        - ticket_id: str
        - ticket_content: str
        """
        findings = context.get("dependency_results", {})
        ticket_content = context["ticket_content"]
        ticket_id = context["ticket_id"]

        # Compile evidence from all subagents
        evidence_summary = _compile_evidence(findings)

        # --- First pass: generate RCA ---
        rca = self._generate_rca(ticket_content, evidence_summary, ticket_id)

        # --- D4.6: Second-instance review ---
        # Self-review limitation: same reasoning that produced the RCA will miss its own errors
        # Independent instance only sees the RCA output, not the generation context
        reviewed_rca = self._independent_review(rca)

        return reviewed_rca

    def _generate_rca(self, ticket: str, evidence: str, ticket_id: str) -> RCAOutput:
        """First pass: generate RCA using forced tool output."""

        system = f"""You are an expert SRE generating a Root Cause Analysis report.
{SEVERITY_CRITERIA}
{FEW_SHOT_EXAMPLES}

Be precise. Use only the evidence provided. Do not invent facts."""

        # D4.3: tool_choice forced — most reliable structured output method
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system,
            messages=[{
                "role": "user",
                "content": f"Ticket {ticket_id}:\n{ticket}\n\nEvidence:\n{evidence}"
            }],
            tools=[_rca_tool_schema()],
            tool_choice={"type": "tool", "name": "generate_rca"},  # D4.3 forced
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "generate_rca":
                return RCAOutput(**block.input, ticket_id=ticket_id)

        raise ValueError("Report generator failed to produce structured output")

    def _independent_review(self, rca: RCAOutput) -> RCAOutput:
        """
        D4.6: Multi-instance review — fresh Claude instance reviews the RCA.
        This instance has NO knowledge of how the RCA was generated.
        It only sees the output and checks for logical consistency.
        """
        review_response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",  # cheap for review pass
            max_tokens=512,
            system="""You are a QA reviewer for incident RCA reports.
Check for:
1. Does the root_cause logically follow from the evidence?
2. Is the severity appropriate given the criteria?
3. Is confidence calibrated (>0.65 if evidence is strong, <0.65 if gaps exist)?
4. Are next_steps actionable and specific?

Return JSON: {"approved": true/false, "issues": ["..."], "adjusted_confidence": 0.0-1.0}""",
            messages=[{"role": "user", "content": f"Review this RCA:\n{rca.model_dump_json(indent=2)}"}],
        )

        try:
            review_text = ""
            for block in review_response.content:
                if hasattr(block, "text"):
                    review_text = block.text
            review = json.loads(review_text)

            # Apply confidence adjustment from independent reviewer
            if "adjusted_confidence" in review:
                rca.confidence = review["adjusted_confidence"]
            if not review.get("approved") and rca.confidence >= 0.65:
                # Reviewer flagged issues — downgrade confidence
                rca.confidence = min(rca.confidence, 0.64)
                rca.escalate = True
                rca.escalation_reason = f"Independent review flagged: {'; '.join(review.get('issues', []))}"
        except (json.JSONDecodeError, KeyError):
            pass  # Review parse failed — keep original RCA unchanged

        return rca


def _compile_evidence(findings: dict) -> str:
    """Compile findings from all subagents into a structured summary."""
    parts = []
    for agent_name, result in findings.items():
        if isinstance(result, dict) and result.get("findings"):
            parts.append(f"=== {agent_name.upper()} ===")
            for f in result["findings"]:
                parts.append(f"- {f.get('fact', str(f))} [source: {f.get('source', 'unknown')}]")
    return "\n".join(parts) or "No evidence collected"


def _rca_tool_schema() -> dict:
    """D4.3: JSON schema for forced structured output."""
    return {
        "name": "generate_rca",
        "description": "Generate a structured Root Cause Analysis report",
        "input_schema": {
            "type": "object",
            "properties": {
                "root_cause": {"type": "string", "description": "Precise root cause statement"},
                "severity": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fact": {"type": "string"},
                            "source": {"type": "string"},
                            "ts": {"type": "string"},
                        },
                        "required": ["fact", "source"],
                    }
                },
                "next_steps": {"type": "array", "items": {"type": "string"}},
                "escalate": {"type": "boolean"},
                "escalation_reason": {"type": "string", "nullable": True},
            },
            "required": ["root_cause", "severity", "confidence", "evidence", "next_steps", "escalate"],
        }
    }
