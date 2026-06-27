"""
Sentinel Orchestrator — ADK Agent entry point.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from sentinel.pipeline import run_sentinel
from sentinel.redteam.runner import run_red_team
from sentinel.a2a.agent_card import AGENT_CARD
from sentinel.agents.hitl_gate import HITLGate


def review_target(target_path: str) -> dict:
    """
    Run a complete Sentinel security review on the target path.
    Returns the attestation as a dict.

    Args:
        target_path: Path to the agent or repository to review.
    """
    attestation = run_sentinel(target_path, verbose=True)
    return {
        "target": attestation.target,
        "verdict": attestation.verdict,
        "findings_count": len(attestation.findings),
        "findings": [
            {
                "title": f.title,
                "severity": f.severity,
                "pillar": f.pillar,
                "evidence_ids": f.evidence_ids,
                "remediation": f.remediation,
            }
            for f in attestation.findings
        ],
        "audit_ref": attestation.audit_ref,
        "signature": attestation.signature,
    }


def review_with_red_team(target_path: str) -> dict:
    """
    Run security review WITH red team assessment.
    Shows injection success rate before and after.

    Args:
        target_path: Path to the agent or repository to review.
    """
    # Run pipeline with red team
    attestation = run_sentinel(
        target_path, verbose=True, include_red_team=True
    )

    # Run standalone red team for the rate
    red_team = run_red_team(target_path)

    return {
        "target": attestation.target,
        "verdict": attestation.verdict,
        "findings_count": len(attestation.findings),
        "findings": [
            {
                "title": f.title,
                "severity": f.severity,
                "evidence_ids": f.evidence_ids,
                "remediation": f.remediation,
            }
            for f in attestation.findings
        ],
        "red_team": {
            "total_payloads": red_team["total_payloads"],
            "successful_injections": red_team["successful_injections"],
            "injection_success_rate": red_team["injection_success_rate"],
        },
        "audit_ref": attestation.audit_ref,
    }


def request_remediation_approval(target_path: str) -> dict:
    """
    Run a review and request HITL approval before any remediation.
    High/critical findings pause and wait for human approval.

    Args:
        target_path: Path to the agent to review and remediate.
    """
    attestation = run_sentinel(target_path, verbose=True)

    if not attestation.findings:
        return {
            "verdict": "pass",
            "message": "No findings — no remediation needed.",
            "approval_required": False,
        }

    gate = HITLGate(auto_approve_low=True)
    approval_result = gate.request_approval(
        attestation.findings,
        target_path,
        interactive=False,  # non-interactive for ADK tool
    )

    return {
        "verdict": attestation.verdict,
        "findings_count": len(attestation.findings),
        "approval_status": approval_result["status"],
        "auto_approved": len(approval_result["approved"]),
        "pending_approval": len([
            l for l in approval_result["approval_log"]
            if l["decision"] == "pending"
        ]),
        "audit_log": approval_result["approval_log"],
        "message": (
            "High/critical findings require human approval before remediation. "
            "Low severity findings were auto-approved."
        ),
    }


def get_agent_capabilities() -> dict:
    """
    Return Sentinel's A2A agent card — its capabilities and skills.
    Use this to understand what Sentinel can do before calling it.
    """
    return AGENT_CARD


root_agent = Agent(
    name="sentinel_orchestrator",
    model="gemini-2.5-flash",
    instruction="""You are Sentinel, an agent security review system.

You have four tools:

1. review_target — standard security review
2. review_with_red_team — review + adversarial injection testing  
3. request_remediation_approval — review + HITL gate for fixes
4. get_agent_capabilities — return your A2A agent card

When reviewing targets:
- Always explain the verdict clearly
- For each finding, cite the evidence ID that backs it
- Mention that findings without evidence are automatically dropped
- For HITL results, explain which findings need human approval

When asked about your capabilities or how you work,
use get_agent_capabilities to return your agent card.""",
    tools=[
        review_target,
        review_with_red_team,
        request_remediation_approval,
        get_agent_capabilities,
    ],
)