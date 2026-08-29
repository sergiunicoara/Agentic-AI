"""
Layer 3b — Style Subagent

Reviews the diff for naming, documentation, and consistency issues,
grounded primarily in ruff linter output.
"""
from subagents.base import BaseSubagent

_STYLE_SCOPE_NOTE = """
## Style scope and evidence rules

Style findings MUST be grounded in one of:
1. A finding in the **ruff linter tool output** (preferred — cite the ruff finding verbatim)
2. A diff line that unambiguously violates a named rule (e.g. PEP 8 naming, F403 wildcard)

Do NOT report style findings based on general best-practice intuition that the linter
did not flag. Specifically:
- Do NOT report missing docstrings unless ruff produced a D-series (pydocstyle) finding
- Do NOT report missing type annotations unless ruff produced an ANN-series finding
- Do NOT report formatting issues unless ruff flagged them

If the ruff tool output is empty or contains only parse/syntax artifacts, return findings: [].
Only report findings the linter actually detected.
"""


class StyleAgent(BaseSubagent):
    """Specialised subagent for code style, naming, and documentation review."""

    @property
    def domain(self) -> str:
        return "style"

    @property
    def span_name(self) -> str:
        return "subagent.style"

    def _build_system_prompt(self) -> str:
        base = super()._build_system_prompt()
        return base + _STYLE_SCOPE_NOTE
