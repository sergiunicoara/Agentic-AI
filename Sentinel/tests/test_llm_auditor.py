"""
Tests for the LLM Auditor — the one auditor whose candidates can actually
be hallucinated. We mock the model call (no live credentials in CI/tests)
and prove the Adjudicator drops what the LLM auditor cannot support.
"""
import json
from unittest.mock import MagicMock, patch

from sentinel.agents.llm_auditor import audit_with_llm
from sentinel.agents.adjudicator import adjudicate
from sentinel.models.schemas import Evidence

REAL_EVIDENCE = [
    Evidence(
        evidence_id="ev_bandit_real_001",
        source="bandit",
        locator="targets/t1_injection/agent.py:13",
        raw={"test_id": "B307", "issue_text": "eval() usage"},
    ),
]


def test_audit_with_llm_returns_empty_without_genai_installed():
    """If google.genai can't be imported, fail safe to no candidates."""
    with patch.dict("sys.modules", {"google.genai": None, "google": None}):
        result = audit_with_llm(REAL_EVIDENCE, "targets/t1_injection")
    assert result == []


def test_audit_with_llm_returns_empty_on_api_failure():
    """Any failure calling the model must not raise — pipeline must not depend on it."""
    with patch("google.genai.Client", side_effect=RuntimeError("no credentials")):
        result = audit_with_llm(REAL_EVIDENCE, "targets/t1_injection")
    assert result == []


def _mock_genai_client(response_text: str):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


def test_llm_candidate_with_real_evidence_id_survives_gate():
    """A model-proposed finding that cites real evidence must survive."""
    llm_response = json.dumps([{
        "finding_id": "llm_find_1",
        "pillar": 3,
        "severity": "high",
        "confidence": 0.9,
        "title": "eval() of untrusted input",
        "rationale": "eval() is called on data that may originate from a tool result",
        "evidence_ids": ["ev_bandit_real_001"],
        "remediation": "Replace eval() with ast.literal_eval()",
    }])

    with patch("google.genai.Client", return_value=_mock_genai_client(llm_response)):
        candidates = audit_with_llm(REAL_EVIDENCE, "targets/t1_injection")

    assert len(candidates) == 1

    evidence_dicts = [e.model_dump() for e in REAL_EVIDENCE]
    attestation = adjudicate(candidates, evidence_dicts, "targets/t1_injection")
    assert len(attestation.findings) == 1


def test_llm_hallucinated_evidence_id_is_dropped_by_gate():
    """
    THE KEY TEST for the LLM auditor.
    The model invents a plausible finding citing an evidence_id that does
    not exist in the real evidence store. The Adjudicator must drop it.
    This is the gate doing its actual job, not unit-tested in the abstract.
    """
    llm_response = json.dumps([{
        "finding_id": "llm_find_hallucinated",
        "pillar": 5,
        "severity": "critical",
        "confidence": 0.95,
        "title": "Authentication bypass in session handling",
        "rationale": "The model asserts this without grounding it in a real scan result",
        "evidence_ids": ["ev_invented_by_model_999"],
        "remediation": "Review session handling",
    }])

    with patch("google.genai.Client", return_value=_mock_genai_client(llm_response)):
        candidates = audit_with_llm(REAL_EVIDENCE, "targets/t1_injection")

    assert len(candidates) == 1  # the LLM did propose it

    evidence_dicts = [e.model_dump() for e in REAL_EVIDENCE]
    attestation = adjudicate(candidates, evidence_dicts, "targets/t1_injection")

    # ...but it must not survive adjudication.
    assert len(attestation.findings) == 0
    assert attestation.verdict == "pass"


def test_llm_response_wrapped_in_markdown_fence_is_parsed():
    """Models often wrap JSON in ```json fences — must still parse."""
    fenced = "```json\n[]\n```"
    with patch("google.genai.Client", return_value=_mock_genai_client(fenced)):
        candidates = audit_with_llm(REAL_EVIDENCE, "targets/t1_injection")
    assert candidates == []
