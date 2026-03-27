"""
Layer 3b — Security Subagent

Reviews the diff for OWASP Top 10 vulnerabilities, grounded in bandit scanner output.
"""
from subagents.base import BaseSubagent


class SecurityAgent(BaseSubagent):
    """Specialised subagent for security review (OWASP Top 10)."""

    @property
    def domain(self) -> str:
        return "security"

    @property
    def span_name(self) -> str:
        return "subagent.security"
