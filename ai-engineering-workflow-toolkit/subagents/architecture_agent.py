"""
Layer 3b — Architecture Subagent

Reviews the diff for SOLID violations, coupling issues, and layer boundary violations,
grounded in linter and type checker output.
"""
from subagents.base import BaseSubagent

# Architecture concerns are MODULE/CLASS-level design decisions:
#   - Class responsibility violations (SRP, god class)
#   - Inter-component coupling (importing concrete infra types into business logic)
#   - Layer boundary breaches (e.g. persistence logic leaking into domain layer)
#   - Dependency direction violations (DIP: depending on concrete instead of abstract)
#
# NOT architecture concerns (belong to style or security):
#   - Magic numbers inside a function body
#   - Single-function dependency usage patterns
#   - Missing docstrings / type annotations
#   - Variable naming
_ARCH_SCOPE_NOTE = """
## Architecture scope clarification

Architecture findings MUST concern **module or class level** design:
- Class with too many responsibilities (god class / SRP violation)
- Direct import of a concrete infrastructure type into a business/domain class
- Violation of layer boundaries (e.g. DB query inside a controller method)
- Dependency Inversion Principle: instantiating a concrete dependency inside `__init__`

Do NOT report as architecture findings:
- Magic numbers or hard-coded literals inside a function body (that is a style concern)
- A single function calling another function or method (that is normal code)
- Missing type annotations or missing docstrings (style domain)
- Any finding that requires seeing more than the diff provides

If the diff adds or modifies a function body only (not a class definition, not an import,
not a module-level structure), the bar for an architecture finding is very high.
Return findings: [] unless a clear class/module-level design violation is unambiguous.
"""


class ArchitectureAgent(BaseSubagent):
    """Specialised subagent for architecture and structural design review."""

    @property
    def domain(self) -> str:
        return "architecture"

    @property
    def span_name(self) -> str:
        return "subagent.architecture"

    def _build_system_prompt(self) -> str:
        base = super()._build_system_prompt()
        return base + _ARCH_SCOPE_NOTE
