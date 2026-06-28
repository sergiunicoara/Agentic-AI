"""
Target T6 — Server-Side Request Forgery via tool-output-driven fetch
(seeded vulnerability).

This is deliberately a tool/dependency blind spot, not a bandit blind
spot accident: bandit has no built-in rule for "URL parameter passed
unvalidated to requests.get" because it's a data-flow / business-logic
issue, not a known-dangerous-call pattern. Catching this requires either
a semgrep rule written for this exact shape (see
sentinel/mcp/semgrep_rules/agent_security.yaml::sentinel-ssrf-unvalidated-url)
or an LLM auditor reasoning about what the code does — which is exactly
the gap Sentinel's semgrep + LLM auditor layers are meant to close beyond
bandit/ruff/pip-audit.
"""
import requests

# Also a hardcoded LLM key. Bandit's hardcoded-password check (B105) only
# matches variable names against password|pass|passwd|pwd|secret|token —
# "key" is not in that list, so a constant like this slips past bandit
# entirely. A value-format rule (sentinel-llm-api-key-hardcoded) catches
# it by recognizing the key's shape instead of the variable's name.
PROVIDER_API_KEY = "sk-proj-abc123def456ghi789jkl"


def fetch_referenced_url(tool_output: str) -> str:
    """
    UNSAFE: fetches whatever URL appears in tool_output with no allowlist,
    no scheme restriction, and no protection against internal/metadata
    endpoints (e.g. http://169.254.169.254/latest/meta-data/). An upstream
    tool result (or an attacker who can influence it) fully controls where
    this agent makes outbound requests.
    """
    response = requests.get(tool_output, timeout=5)
    return response.text


def summarize_page(url: str) -> dict:
    """UNSAFE: same SSRF shape via a second entry point."""
    page = requests.get(url)
    return {"length": len(page.text), "status": page.status_code}
