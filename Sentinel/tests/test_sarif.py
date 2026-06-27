"""
Tests for SARIF export — the CI security-gate integration format.
"""
import json
from sentinel.eval.sarif import attestation_to_sarif
from sentinel.agents.adjudicator import adjudicate

REAL_EVIDENCE = [
    {
        "evidence_id": "ev_bandit_001",
        "source": "bandit",
        "locator": "targets/t1_injection/agent.py:13",
        "raw": {"test_id": "B307"},
    },
]

CANDIDATE = {
    "finding_id": "find-001",
    "pillar": 3,
    "severity": "high",
    "confidence": 0.95,
    "title": "Unsafe eval usage",
    "rationale": "eval() called on user input",
    "evidence_ids": ["ev_bandit_001"],
    "remediation": "Remove eval()",
}


def test_sarif_log_has_required_top_level_keys():
    attestation = adjudicate([CANDIDATE], REAL_EVIDENCE, "targets/t1_injection")
    sarif = attestation_to_sarif(attestation)
    assert sarif["version"] == "2.1.0"
    assert "runs" in sarif
    assert len(sarif["runs"]) == 1


def test_sarif_result_traces_to_evidence_id():
    """Every SARIF result must carry the same evidence_ids as the Attestation."""
    attestation = adjudicate([CANDIDATE], REAL_EVIDENCE, "targets/t1_injection")
    sarif = attestation_to_sarif(attestation)
    results = sarif["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["properties"]["evidence_ids"] == ["ev_bandit_001"]


def test_sarif_is_json_serializable():
    """The SARIF log must be valid JSON (CI tools parse it directly)."""
    attestation = adjudicate([CANDIDATE], REAL_EVIDENCE, "targets/t1_injection")
    sarif = attestation_to_sarif(attestation)
    json.dumps(sarif)  # must not raise


def test_empty_attestation_produces_empty_results():
    attestation = adjudicate([], [], "targets/c1_clean")
    sarif = attestation_to_sarif(attestation)
    assert sarif["runs"][0]["results"] == []
