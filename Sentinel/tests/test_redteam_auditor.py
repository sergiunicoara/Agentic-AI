"""
Tests for the RedTeamAuditor — converts redteam_trajectory evidence
into evidence-backed findings.
"""
from sentinel.agents.redteam_auditor import audit_for_redteam
from sentinel.models.schemas import Evidence

REDTEAM_EVIDENCE = [
    Evidence(
        evidence_id="ev_redteam_001",
        source="redteam_trajectory",
        locator="targets/t1_injection/agent.py:13",
        raw={
            "payload_id": "inj_002",
            "payload_name": "Eval injection via user input",
            "vector": "eval_surface",
            "vulnerable_locations": ["targets/t1_injection/agent.py:13"],
            "payload_preview": "__import__('os').system('whoami')",
        },
    ),
]

NON_REDTEAM_EVIDENCE = [
    Evidence(
        evidence_id="ev_bandit_001",
        source="bandit",
        locator="targets/t1_injection/agent.py:13",
        raw={"test_id": "B307"},
    ),
]


def test_redteam_evidence_produces_finding():
    """Trajectory evidence must produce a candidate finding referencing it."""
    candidates = audit_for_redteam(REDTEAM_EVIDENCE)
    assert len(candidates) == 1
    assert candidates[0]["evidence_ids"] == ["ev_redteam_001"]
    assert "Eval injection via user input" in candidates[0]["title"]


def test_non_redteam_evidence_is_ignored():
    """The red team auditor must only act on redteam_trajectory evidence."""
    candidates = audit_for_redteam(NON_REDTEAM_EVIDENCE)
    assert candidates == []


def test_redteam_finding_survives_adjudication():
    """A red-team-sourced finding must survive the gate like any other."""
    from sentinel.agents.adjudicator import adjudicate

    candidates = audit_for_redteam(REDTEAM_EVIDENCE)
    evidence_dicts = [e.model_dump() for e in REDTEAM_EVIDENCE]
    attestation = adjudicate(candidates, evidence_dicts, "targets/t1_injection")

    assert len(attestation.findings) == 1
    assert attestation.findings[0].evidence_ids == ["ev_redteam_001"]
