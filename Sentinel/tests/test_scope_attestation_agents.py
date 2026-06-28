"""
Tests for the Scope and Attestation ADK agents and their wired tools.

These two agents were previously defined but never invoked (dead code).
They're now real ADK agents whose tools (profile_target, produce_attestation)
are exposed on the orchestrator. These tests prove the tools actually work
and that the agents are wired into the orchestrator's tool list — so the
"multi-agent ADK system" claim is backed by behavior, not just files.
"""
import json

from sentinel.agents.scope_agent import scope_agent, profile_target
from sentinel.agents.attestation_agent import attestation_agent, produce_attestation
from sentinel.agents.evidence_agent import collect_evidence
from sentinel.agents.injection_auditor import audit_for_injection


def test_profile_target_selects_skills():
    result = profile_target("targets/t1_injection")
    assert "prompt-injection-defense" in result["selected_skills"]
    assert result["skill_count"] >= 1
    assert all("name" in d for d in result["skill_details"])


def test_produce_attestation_runs_the_gate():
    """produce_attestation must run the adjudicator and return a signed verdict."""
    evidence = collect_evidence("targets/t1_injection")
    candidates = audit_for_injection(evidence)
    evidence_json = json.dumps([e.model_dump() for e in evidence])

    result = produce_attestation(json.dumps(candidates), evidence_json, "targets/t1_injection")

    assert result["verdict"] == "fail"
    assert result["findings_count"] > 0
    assert result["signature"].startswith("sentinel-")
    assert result["audit_ref"].startswith("audit-")


def test_produce_attestation_drops_unsupported_finding():
    """A candidate citing a fake evidence_id must not survive the gate."""
    fake_candidate = [{
        "finding_id": "fake-1", "pillar": 3, "severity": "high",
        "confidence": 0.9, "title": "made up", "rationale": "no evidence",
        "evidence_ids": ["ev_does_not_exist"],
    }]
    result = produce_attestation(json.dumps(fake_candidate), "[]", "targets/c1_clean")
    assert result["findings_count"] == 0
    assert result["verdict"] == "pass"


def test_produce_attestation_handles_bad_json():
    result = produce_attestation("not valid json", "[]", "x")
    assert "error" in result


def test_agents_are_real_adk_agents():
    from google.adk.agents import Agent
    assert isinstance(scope_agent, Agent)
    assert isinstance(attestation_agent, Agent)


def test_agents_wired_into_orchestrator():
    """The two agents' tools must actually be on the orchestrator — proof
    they're invoked, not dead code."""
    from sentinel.orchestrator.agent import root_agent
    tool_names = [getattr(t, "__name__", "") for t in root_agent.tools]
    assert "profile_target" in tool_names
    assert "produce_attestation" in tool_names
