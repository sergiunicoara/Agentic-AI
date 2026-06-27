"""
Sentinel A2A Agent Card.

Publishes Sentinel's capabilities in the A2A protocol format.
Any A2A-compatible agent can discover and call Sentinel
by fetching this card from /.well-known/agent-card.json
"""
from datetime import datetime

AGENT_CARD = {
    "name": "Sentinel",
    "version": "1.0.0",
    "description": (
        "Hallucination-free security review for vibe-coded agents. "
        "Every finding traces to deterministic tool evidence. "
        "Hallucinated findings are automatically dropped."
    ),
    "url": "http://localhost:8080",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "stateTransitionHistory": True,
    },
    "skills": [
        {
            "id": "security-review",
            "name": "Security Review",
            "description": (
                "Run a complete security review on an agent or repository. "
                "Returns an attestation with evidence-backed findings only."
            ),
            "inputModes": ["text"],
            "outputModes": ["text"],
            "examples": [
                "Review the agent at /path/to/agent",
                "Scan targets/my_agent for security issues",
            ],
        },
        {
            "id": "red-team",
            "name": "Red Team Assessment",
            "description": (
                "Fire adversarial injection payloads at a target agent "
                "and report the injection success rate."
            ),
            "inputModes": ["text"],
            "outputModes": ["text"],
        },
    ],
    "provider": {
        "name": "Sergiu Nicoara",
        "url": "https://github.com/sergiunicoara/sentinel",
    },
    "published": datetime.utcnow().isoformat() + "Z",
}