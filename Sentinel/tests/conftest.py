"""Shared test configuration for deterministic scanner integration tests."""

import pytest

import sentinel.mcp.evidence_server as evidence_server


@pytest.fixture(autouse=True)
def use_local_semgrep_rules_in_tests(monkeypatch):
    """Keep tests offline while production retains best-effort registry packs."""
    monkeypatch.setattr(
        evidence_server,
        "SEMGREP_CONFIG_GROUPS",
        [[str(evidence_server._SEMGREP_RULES_DIR)]],
    )
    monkeypatch.setattr(evidence_server, "_registry_packs_unavailable", False)
