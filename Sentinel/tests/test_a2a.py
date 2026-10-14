"""
A2A tests — agent card structure, freshness, and discovery-endpoint parity.
"""
import importlib

import pytest
from fastapi.testclient import TestClient

from sentinel.a2a.agent_card import AGENT_CARD, build_agent_card


def test_agent_card_has_required_fields():
    """Agent card must have all A2A required fields."""
    assert "name" in AGENT_CARD
    assert "version" in AGENT_CARD
    assert "description" in AGENT_CARD
    assert "url" in AGENT_CARD
    assert "capabilities" in AGENT_CARD
    assert "skills" in AGENT_CARD
    assert "protocolVersion" in AGENT_CARD
    assert "preferredTransport" in AGENT_CARD


def test_agent_card_has_skills():
    """Agent card must declare at least one skill."""
    assert len(AGENT_CARD["skills"]) > 0
    for skill in AGENT_CARD["skills"]:
        assert "id" in skill
        assert "name" in skill
        assert "description" in skill


def test_agent_card_security_review_skill_exists():
    """Security review skill must be declared."""
    skill_ids = [s["id"] for s in AGENT_CARD["skills"]]
    assert "security-review" in skill_ids


def test_agent_card_has_provider():
    """Agent card must identify the provider."""
    assert "provider" in AGENT_CARD
    assert "organization" in AGENT_CARD["provider"]


def test_agent_card_streaming_capability_declared():
    assert AGENT_CARD["capabilities"]["streaming"] is True
    assert AGENT_CARD["capabilities"]["pushNotifications"] is False


def test_agent_card_no_security_scheme_when_token_unset(monkeypatch):
    monkeypatch.delenv("SENTINEL_A2A_TOKEN", raising=False)
    card = build_agent_card()
    assert card["securitySchemes"] == {}
    assert card["security"] == []


def test_agent_card_declares_bearer_scheme_when_token_set(monkeypatch):
    monkeypatch.setenv("SENTINEL_A2A_TOKEN", "secret123")
    card = build_agent_card()
    assert card["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert card["security"] == [{"bearerAuth": []}]


def test_agent_card_url_reflects_public_url_env(monkeypatch):
    monkeypatch.setenv("SENTINEL_PUBLIC_URL", "https://sentinel.example.com")
    card = build_agent_card()
    assert card["url"] == "https://sentinel.example.com/a2a"


def test_agent_card_is_deterministic():
    """No per-request fields, so clients can cache the card."""
    assert build_agent_card() == build_agent_card()


def test_agent_card_modes_are_mime_types_matching_server_output():
    card = build_agent_card()
    assert card["defaultOutputModes"] == ["application/json"]
    for skill in card["skills"]:
        assert skill["inputModes"] == ["text/plain"]
        assert skill["outputModes"] == ["application/json"]


def test_agent_card_red_team_skill_documents_how_to_trigger_it():
    red_team = next(s for s in build_agent_card()["skills"] if s["id"] == "red-team")
    assert "include_red_team" in red_team["description"]
    # Live execution is not reachable over A2A, so the card must not advertise it.
    assert "live" not in red_team["description"].lower()


@pytest.fixture
def server_module(monkeypatch):
    monkeypatch.delenv("SENTINEL_A2A_TOKEN", raising=False)
    import sentinel.a2a.server as server
    importlib.reload(server)
    yield server


def test_both_discovery_paths_serve_identical_content(server_module):
    client = TestClient(server_module.app)
    canonical = client.get("/.well-known/agent-card.json")
    alias = client.get("/.well-known/agent.json")
    assert canonical.status_code == 200
    assert alias.status_code == 200
    assert canonical.json() == alias.json()


def test_deployment_check_refuses_public_url_without_token(server_module, monkeypatch):
    monkeypatch.setenv("SENTINEL_PUBLIC_URL", "https://sentinel.example.com")
    monkeypatch.delenv("SENTINEL_A2A_TOKEN", raising=False)
    monkeypatch.delenv("SENTINEL_A2A_ALLOW_UNAUTHENTICATED", raising=False)
    with pytest.raises(SystemExit):
        server_module.check_deployment_config()


def test_deployment_check_allows_token_or_explicit_opt_out(server_module, monkeypatch):
    monkeypatch.setenv("SENTINEL_PUBLIC_URL", "https://sentinel.example.com")
    monkeypatch.setenv("SENTINEL_A2A_TOKEN", "secret123")
    server_module.check_deployment_config()
    monkeypatch.delenv("SENTINEL_A2A_TOKEN")
    monkeypatch.setenv("SENTINEL_A2A_ALLOW_UNAUTHENTICATED", "1")
    server_module.check_deployment_config()


def test_deployment_check_allows_local_default(server_module, monkeypatch):
    monkeypatch.delenv("SENTINEL_PUBLIC_URL", raising=False)
    monkeypatch.delenv("SENTINEL_A2A_TOKEN", raising=False)
    server_module.check_deployment_config()
