"""
Sentinel A2A Agent Card.

Publishes Sentinel's capabilities in the A2A protocol format. Any
A2A-compatible agent can discover Sentinel at either well-known path:

  - GET /.well-known/agent-card.json  (canonical per the current A2A spec)
  - GET /.well-known/agent.json       (compatibility alias for older
    A2A drafts that used this path)

`build_agent_card()` is called fresh on every request so `published` and
`url` are never stale (the previous version computed both once at import
time). `AGENT_CARD` is kept as a module-level constant, built once at
import, purely for the orchestrator's in-process tool
(`sentinel/orchestrator/agent.py`), which doesn't need per-request
freshness.
"""
import os


def build_agent_card(base_url: str | None = None) -> dict:
    from datetime import datetime, timezone

    base_url = base_url or os.environ.get("SENTINEL_PUBLIC_URL", "http://localhost:8080")
    token_configured = bool(os.environ.get("SENTINEL_A2A_TOKEN"))

    return {
        "protocolVersion": "0.3.0",
        "name": "Sentinel",
        "version": "1.0.0",
        "description": (
            "Hallucination-free security review for vibe-coded agents. "
            "Every finding traces to deterministic tool evidence (bandit, "
            "ruff, pip-audit, semgrep). Hallucinated findings are "
            "automatically dropped by the Adjudicator gate."
        ),
        "url": f"{base_url}/a2a",
        "preferredTransport": "JSONRPC",
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text", "application/json"],
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "securitySchemes": (
            {"bearerAuth": {"type": "http", "scheme": "bearer"}} if token_configured else {}
        ),
        "security": [{"bearerAuth": []}] if token_configured else [],
        "skills": [
            {
                "id": "security-review",
                "name": "Security Review",
                "description": (
                    "Run a complete security review on an agent or repository. "
                    "Returns an attestation with evidence-backed findings only."
                ),
                "tags": ["security", "sast", "attestation"],
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
                    "Fire adversarial injection payloads at a target agent and "
                    "report the injection success rate. Static (surface match) "
                    "by default; live mode actually executes payloads against "
                    "the target's real functions in a sandboxed subprocess."
                ),
                "tags": ["security", "red-team", "injection"],
                "inputModes": ["text"],
                "outputModes": ["text"],
            },
        ],
        "provider": {
            "name": "Sergiu Nicoara",
            "url": "https://github.com/sergiunicoara/sentinel",
        },
        "published": datetime.now(timezone.utc).isoformat(),
    }


AGENT_CARD = build_agent_card()
