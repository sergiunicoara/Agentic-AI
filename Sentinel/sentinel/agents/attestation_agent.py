"""
Attestation Agent — produces the final risk-stratified attestation.
Real ADK LlmAgent that interprets findings and signs the verdict.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from sentinel.agents.adjudicator import adjudicate
import json


def produce_attestation(
    candidate_findings_json: str,
    evidence_store_json: str,
    target_path: str,
) -> dict:
    """
    Run the Adjudicator trust gate and produce a signed attestation.
    Drops any finding without deterministic evidence.

    Args:
        candidate_findings_json: JSON string of candidate findings from auditors
        evidence_store_json: JSON string of evidence items from EvidenceAgent
        target_path: Path to the scanned target
    """
    try:
        candidates = json.loads(candidate_findings_json)
        evidence = json.loads(evidence_store_json)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON input: {e}"}

    attestation = adjudicate(candidates, evidence, target_path)

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
        "signature": attestation.signature,
        "audit_ref": attestation.audit_ref,
    }


attestation_agent = Agent(
    name="attestation_agent",
    model="gemini-2.5-flash",
    instruction="""You are the Attestation Agent — the final stage of
Sentinel's security review pipeline.

You receive candidate findings from specialist auditors and evidence
from the EvidenceAgent. Your job is to:

1. Call produce_attestation with the candidates and evidence
2. The Adjudicator trust gate will DROP any finding without evidence
3. Interpret the surviving findings and the verdict
4. Explain what the attestation means for the target

Always state clearly:
- The verdict (pass / pass_with_findings / fail)
- How many findings were dropped vs survived
- What the audit_ref is for traceability
- That the attestation is signed and immutable

You are the trust anchor of the pipeline. Be precise.""",
    tools=[produce_attestation],
)
