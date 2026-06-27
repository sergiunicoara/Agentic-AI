"""
Tests for the Adjudicator trust gate.
This is the most important test file in the project.
It proves that hallucinated findings are dropped.
"""
from sentinel.agents.adjudicator import adjudicate


# Real evidence from bandit (as if returned by evidence_server)
REAL_EVIDENCE = [
    {
        "evidence_id": "ev_bandit_001",
        "source": "bandit",
        "locator": "targets/t1_injection/agent.py:13",
        "raw": {"test_id": "B307", "issue_severity": "MEDIUM"},
    },
    {
        "evidence_id": "ev_bandit_002",
        "source": "bandit",
        "locator": "targets/t1_injection/agent.py:16",
        "raw": {"test_id": "B602", "issue_severity": "HIGH"},
    },
]


def test_finding_with_valid_evidence_survives():
    """A finding that references real evidence must survive adjudication."""
    candidates = [
        {
            "finding_id": "find-001",
            "pillar": 3,
            "severity": "high",
            "confidence": 0.95,
            "title": "Shell injection via subprocess",
            "rationale": "subprocess.run called with shell=True and user input",
            "evidence_ids": ["ev_bandit_002"],  # real evidence
            "remediation": "Set shell=False",
        }
    ]
    attestation = adjudicate(candidates, REAL_EVIDENCE, "targets/t1_injection")
    assert len(attestation.findings) == 1
    assert attestation.findings[0].title == "Shell injection via subprocess"
    assert attestation.verdict == "fail"  # high severity → fail


def test_finding_without_evidence_is_dropped():
    """
    THE KEY TEST.
    A plausible-sounding finding with no evidence_ids must be DROPPED.
    This is the hallucination gate working.
    """
    candidates = [
        {
            "finding_id": "find-hallucinated",
            "pillar": 3,
            "severity": "critical",
            "confidence": 0.99,
            "title": "SQL Injection in database layer",
            "rationale": "I think there might be SQL injection here",
            "evidence_ids": [],  # NO EVIDENCE — hallucinated finding
        }
    ]
    attestation = adjudicate(candidates, REAL_EVIDENCE, "targets/t1_injection")
    assert len(attestation.findings) == 0  # dropped
    assert attestation.verdict == "pass"   # no findings → pass


def test_finding_with_fake_evidence_id_is_dropped():
    """
    A finding referencing a non-existent evidence_id must be DROPPED.
    The LLM cannot invent evidence IDs.
    """
    candidates = [
        {
            "finding_id": "find-fake-evidence",
            "pillar": 4,
            "severity": "high",
            "confidence": 0.9,
            "title": "Dependency vulnerability",
            "rationale": "Old package with CVE",
            "evidence_ids": ["ev_invented_999"],  # does not exist
        }
    ]
    attestation = adjudicate(candidates, REAL_EVIDENCE, "targets/t1_injection")
    assert len(attestation.findings) == 0  # dropped
    assert attestation.verdict == "pass"


def test_mixed_candidates_only_valid_survive():
    """
    Mix of real and hallucinated findings.
    Only the evidence-backed one must survive.
    """
    candidates = [
        {
            "finding_id": "find-real",
            "pillar": 3,
            "severity": "med",
            "confidence": 0.9,
            "title": "Unsafe eval usage",
            "rationale": "eval() called on user input",
            "evidence_ids": ["ev_bandit_001"],  # real
        },
        {
            "finding_id": "find-hallucinated",
            "pillar": 5,
            "severity": "critical",
            "confidence": 0.99,
            "title": "Authentication bypass",
            "rationale": "I think auth can be bypassed",
            "evidence_ids": [],  # hallucinated
        },
    ]
    attestation = adjudicate(candidates, REAL_EVIDENCE, "targets/t1_injection")
    assert len(attestation.findings) == 1
    assert attestation.findings[0].title == "Unsafe eval usage"
    assert attestation.verdict == "pass_with_findings"


def test_clean_target_gets_pass_verdict():
    """No candidates → pass verdict with empty findings."""
    attestation = adjudicate([], [], "targets/c1_clean")
    assert attestation.verdict == "pass"
    assert len(attestation.findings) == 0
    assert attestation.signature.startswith("sentinel-")
    assert attestation.audit_ref.startswith("audit-")