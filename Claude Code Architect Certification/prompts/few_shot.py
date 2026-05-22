"""
CCA-F D4.2: Few-Shot Prompting
Exam fact: "few-shot examples are the most effective technique for consistently
formatted output" — more effective than just describing the format.

D4.1: Explicit criteria design — specificity over vagueness.
"""
from __future__ import annotations

# D4.2: Few-shot examples for RCA prompting
# These are concrete input/output pairs — the exam says these are the most effective
# communication method for consistent structured output.
FEW_SHOT_RCA_EXAMPLES = [
    {
        "input": "DB connection timeouts at 14:32. CPU spiked to 98% at 14:30. Error: connection pool exhausted.",
        "output": {
            "root_cause": "PostgreSQL connection pool exhausted: slow queries held connections beyond pool timeout (30s), blocking new requests",
            "severity": "P1",
            "confidence": 0.91,
            "evidence": [
                {"fact": "DB CPU reached 98%", "source": "prometheus", "ts": "2026-05-21T14:30:00Z"},
                {"fact": "connection pool exhausted error in app logs", "source": "application_logs", "ts": "2026-05-21T14:32:00Z"},
            ],
            "next_steps": ["Increase connection pool size from 10 to 25", "Add query timeout of 10s", "Enable slow query log"],
            "escalate": False,
        }
    },
    {
        "input": "5% of users getting 500 errors. Intermittent. No specific pattern found. Started around 15:00.",
        "output": {
            "root_cause": "Root cause unclear — either upstream service degradation or memory pressure on worker pool. Conflicting signals.",
            "severity": "P2",
            "confidence": 0.48,
            "evidence": [
                {"fact": "5% error rate starting at 15:00", "source": "application_metrics"},
                {"fact": "No correlated infrastructure alerts", "source": "alerting_system"},
            ],
            "next_steps": ["Enable request tracing for failing requests", "Collect heap dump from worker processes", "Check upstream service health"],
            "escalate": True,
            "escalation_reason": "Confidence 0.48 below threshold 0.65; insufficient evidence for definitive root cause",
        }
    }
]


def build_rca_prompt(ticket_content: str) -> str:
    """
    D4.2: Build few-shot prompt with concrete examples.
    D4.1: Explicit criteria in the prompt (not vague instructions).
    """
    import json

    examples_text = "\n\n".join([
        f"Input: {ex['input']}\nOutput: {json.dumps(ex['output'], indent=2)}"
        for ex in FEW_SHOT_RCA_EXAMPLES
    ])

    return f"""Analyze this incident ticket and produce a Root Cause Analysis.

## Severity Criteria (use EXACTLY these — no interpretation)
P1: Complete outage OR data loss risk, >10% users affected
P2: Significant degradation OR security issue, >1% users affected
P3: Minor degradation, workaround exists, <1% users
P4: Cosmetic issue, no user impact

## Confidence Calibration
>=0.85: Direct evidence with clear causality
0.65-0.84: Strong correlation, minor gaps
<0.65: Insufficient evidence — MUST set escalate=true

## Examples of correct output:
{examples_text}

## Ticket to analyze:
{ticket_content}

Follow the same JSON structure as the examples above exactly."""
