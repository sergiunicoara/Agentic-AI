"""
Attestation Agent — produces the final risk-stratified attestation.
Real ADK LlmAgent that interprets findings and signs the verdict.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from sentinel.agents.adjudicator import adjudicate
from sentinel.agents.evidence_agent import collect_evidence_with_status
from sentinel.mcp.evidence_server import _validate_target, InvalidTargetPath, SCAN_ROOT
import json


def produce_attestation(
    candidate_findings_json: str,
    target_path: str,
) -> dict:
    """
    Run the Adjudicator trust gate and produce an attestation.
    Drops any finding without deterministic evidence.

    The evidence store is NEVER taken from the caller: this tool re-runs the
    deterministic scan of target_path server-side and adjudicates against
    that. Evidence ids are content-addressed, so ids from an earlier scan of
    the same, unchanged target still resolve; fabricated ids never do.

    Args:
        candidate_findings_json: JSON string of candidate findings from auditors
        target_path: Path to the scanned target (inside the scan root)
    """
    try:
        candidates = json.loads(candidate_findings_json)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON input: {e}"}
    if not isinstance(candidates, list):
        return {"error": "candidate_findings_json must be a JSON array"}

    try:
        resolved = _validate_target(target_path)
    except InvalidTargetPath as e:
        attestation = adjudicate(candidates, [], str(target_path),
                                 inconclusive_reasons=[f"invalid target: {e}"])
    else:
        evidence, tool_status = collect_evidence_with_status(str(resolved))
        display_target = resolved.relative_to(SCAN_ROOT).as_posix() if resolved != SCAN_ROOT else "."
        attestation = adjudicate(
            candidates, [e.model_dump() for e in evidence], display_target,
            tool_status=tool_status,
        )

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
        "inconclusive_reasons": attestation.inconclusive_reasons,
        "signature": attestation.signature,
        "audit_ref": attestation.audit_ref,
    }


attestation_agent = Agent(
    name="attestation_agent",
    model="gemini-2.5-flash",
    instruction="""You are the Attestation Agent — the final stage of
Sentinel's security review pipeline.

You receive candidate findings from specialist auditors. Your job is to:

1. Call produce_attestation with the candidates and the target path.
   Sentinel re-runs the deterministic scan itself — you cannot supply
   evidence, only candidate findings that cite evidence ids.
2. The Adjudicator trust gate will DROP any finding that cites no
   evidence, cites any id the scan didn't produce, or cites evidence
   that doesn't match the finding
3. Interpret the surviving findings and the verdict
4. Explain what the attestation means for the target

Always state clearly:
- The verdict (pass / pass_with_findings / fail / inconclusive).
  "inconclusive" means a scanner did not run or the target was invalid —
  it is NOT a pass; list the inconclusive_reasons
- How many findings were dropped vs survived
- What the audit_ref is for traceability
- The signature status: an "hmac-sha256:..." signature can be verified
  with the deployment's SENTINEL_SIGNING_KEY; "unsigned" means no key was
  configured and the attestation is not tamper-evident

You are the trust anchor of the pipeline. Be precise.""",
    tools=[produce_attestation],
)
