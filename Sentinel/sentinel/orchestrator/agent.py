"""
Sentinel Orchestrator — ADK Agent entry point.

This is what `adk run sentinel` calls.
It wraps the Sentinel pipeline as an ADK agent with tools.
"""
import sys
from pathlib import Path

# Add project root to path so 'sentinel' package is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from sentinel.pipeline import run_sentinel


def review_target(target_path: str) -> dict:
    """
    Run a complete Sentinel security review on the target path.
    Returns the attestation as a dict.
    
    Args:
        target_path: Path to the agent or repository to review.
                     Example: 'targets/t1_injection'
    """
    attestation = run_sentinel(target_path)
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


root_agent = Agent(
    name="sentinel_orchestrator",
    model="gemini-2.5-flash",
    instruction="""You are Sentinel, an agent security review system.

When the user provides a target path, call the review_target tool 
to run a complete security review.

After getting results, explain:
1. The overall verdict (pass/fail/pass_with_findings)
2. Each finding with its severity and what evidence backs it
3. Remediation steps for each finding
4. That every finding shown has been verified by deterministic tools

If the verdict is 'pass', confirm the target passed all checks.

Always mention that findings are evidence-backed — 
hallucinated findings are automatically dropped by the Adjudicator.""",
    tools=[review_target],
)