"""
A2A tests — agent card and protocol structure.
"""
from sentinel.a2a.agent_card import AGENT_CARD


def test_agent_card_has_required_fields():
    """Agent card must have all A2A required fields."""
    assert "name" in AGENT_CARD
    assert "version" in AGENT_CARD
    assert "description" in AGENT_CARD
    assert "url" in AGENT_CARD
    assert "capabilities" in AGENT_CARD
    assert "skills" in AGENT_CARD


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
    assert "name" in AGENT_CARD["provider"]