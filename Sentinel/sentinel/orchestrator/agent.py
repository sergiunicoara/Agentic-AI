"""
Sentinel Orchestrator — ADK Agent entry point.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from sentinel.pipeline import run_sentinel
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
    # Run pipeline with red team (single scan — reuse its red team summary
    # instead of re-running run_red_team separately)
    attestation, red_team = run_sentinel(
        target_path, verbose=True, include_red_team=True, return_red_team=True
    )

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
            entry for entry in approval_result["approval_log"]
            if entry["decision"] == "pending"
        ]),
        "audit_log": approval_result["approval_log"],
        "message": (
            "High/critical findings require human approval before remediation. "
            "Low severity findings were auto-approved."
        ),
    }


def review_with_live_red_team(target_path: str) -> dict:
    """
    Run security review with LIVE red team execution: adversarial corpus
    payloads are actually fired at the target's real functions inside a
    sandboxed subprocess (disposable temp cwd, scrubbed env, blocked
    network, hard timeout, POSIX resource limits — see
    sentinel/redteam/live_runner.py for the full safety model), instead
    of only checking for static surfaces.

    Only use this against the bundled, trusted target corpus
    (targets/t1_injection, etc.) — it executes real code paths and is not
    a substitute for a real container/VM sandbox against untrusted code.

    Args:
        target_path: Path to the agent or repository to review.
    """
    attestation = run_sentinel(target_path, verbose=True, include_live_red_team=True)

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
        "audit_ref": attestation.audit_ref,
        "note": (
            "This review actually executed red team payloads against the "
            "target's real functions in a sandboxed subprocess. Findings "
            "titled LIVE-CONFIRMED are empirically proven code execution, "
            "not pattern matches."
        ),
    }


def review_with_llm_auditor(target_path: str) -> dict:
    """
    Run security review WITH the LLM-driven auditor enabled.
    Unlike the other auditors (which are deterministic lookups over tool
    output and can never propose an unsupported finding), the LLM auditor
    reasons freely about the code — so this is the path where the
    Adjudicator's evidence gate actually has something to drop. Use this
    to demonstrate the hallucination-gate working on a real LLM output.

    Args:
        target_path: Path to the agent or repository to review.
    """
    attestation = run_sentinel(target_path, verbose=True, include_llm_auditor=True)
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
        "note": (
            "This review included the LLM-driven auditor. Any candidate "
            "finding it proposed without a real evidence_id was dropped "
            "by the Adjudicator before reaching this result."
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

You have six tools:

1. review_target — standard security review (deterministic auditors only)
2. review_with_red_team — review + adversarial injection testing
   (static surface match — fast, no code execution)
3. review_with_live_red_team — review + LIVE red team execution
   (payloads actually run against the target's real functions, inside a
   sandboxed subprocess; only use against the bundled trusted corpus)
4. review_with_llm_auditor — review + LLM-driven auditor (the one auditor
   whose findings can be hallucinated; use this to demonstrate the
   Adjudicator gate dropping unsupported findings)
5. request_remediation_approval — review + HITL gate for fixes
6. get_agent_capabilities — return your A2A agent card

When reviewing targets:
- Always explain the verdict clearly
- For each finding, cite the evidence ID that backs it
- Mention that findings without evidence are automatically dropped
- For live red team findings, mention they're empirically confirmed via
  sandboxed execution, not a static pattern match
- For HITL results, explain which findings need human approval

When asked about your capabilities or how you work,
use get_agent_capabilities to return your agent card.""",
    tools=[
        review_target,
        review_with_red_team,
        review_with_live_red_team,
        review_with_llm_auditor,
        request_remediation_approval,
        get_agent_capabilities,
    ],
)