"""
Layer 3b: Subagent Base Class

All three specialised subagents share the same interaction pattern:
1. Receive the diff and MCP tool output
2. Inject the appropriate skill as a system prompt <skill> block
3. Call Claude with a structured output request
4. Return a validated SubagentVerdict dict

The key architectural constraint is enforced here: every finding must have
an `evidence` field that quotes tool output or a diff line.
"""
import json
import os
import time
from abc import ABC, abstractmethod

import anthropic

from observability.tracer import get_tracer

_MODEL = os.getenv("SUBAGENT_MODEL", "claude-sonnet-4-6")

tracer = get_tracer("subagents")

_VERDICT_SCHEMA = {
    "name": "subagent_verdict",
    "description": "Structured verdict from a specialised code review subagent",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "enum": ["security", "architecture", "style"],
                "description": "The review domain this agent covers",
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "file": {"type": "string"},
                        "line": {"type": ["integer", "null"]},
                        "severity": {"type": "string", "enum": ["error", "warning", "info"]},
                        "rule": {"type": "string"},
                        "message": {"type": "string"},
                        "evidence": {
                            "type": "string",
                            "description": "Direct quote from tool output or diff line that grounds this finding",
                        },
                    },
                    "required": ["id", "file", "severity", "rule", "message", "evidence"],
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["domain", "findings", "summary"],
    },
}


class BaseSubagent(ABC):
    """Base class for specialised review subagents."""

    def __init__(self, skill_content: str):
        self.skill_content = skill_content
        self.client = anthropic.Anthropic()

    @property
    @abstractmethod
    def domain(self) -> str:
        """One of: security, architecture, style"""

    @property
    @abstractmethod
    def span_name(self) -> str:
        """OpenTelemetry span name."""

    def _build_system_prompt(self) -> str:
        skill_block = f"\n<skill>\n{self.skill_content}\n</skill>\n" if self.skill_content else ""
        return f"""You are a specialised code reviewer focused exclusively on {self.domain} concerns.
{skill_block}
## Hard constraints

1. DOMAIN SCOPE: Only report findings in the `{self.domain}` domain. Do NOT comment on other
   domains even if you notice issues there.

2. TRACEABILITY: Every finding MUST have an `evidence` field quoting either:
   - A specific tool output entry (verbatim), OR
   - A specific line from the diff (verbatim, starting with + or -)
   Findings without direct evidence are REJECTED downstream. When in doubt, omit the finding.

3. INCOMPLETE CODE: The diff may be a small snippet without full context (missing imports,
   incomplete classes, etc.). Tool errors like "syntax error", "cannot import", or "undefined
   name" on such snippets are ARTIFACTS, not real issues. Do NOT report findings based on these
   tool errors. If the tool output only contains syntax/parse errors, treat it as empty.

4. DIFF-LINES ONLY: Report ONLY findings that are directly evidenced by lines starting with `+`
   in the diff. Do NOT report findings based on unchanged context lines (`-` or ` ` prefix).
   Do NOT infer, extrapolate, or report secondary/cascading implications. If the primary issue
   visible in the diff does not fall within the `{self.domain}` domain, return findings: [].

5. MINIMAL FINDINGS: Prefer fewer, high-confidence findings over many speculative ones.
   A single added line is never sufficient evidence for a structural or architectural violation
   unless the problematic pattern is completely visible in that line.

Respond using the subagent_verdict tool. Return an empty findings list if you have no
confident, directly-evidenced findings in the {self.domain} domain.
"""

    def _build_user_message(self, diff: str, tool_output: dict) -> str:
        # Check if any tool ran on partial/temp files (diff snippets)
        partial = any(
            v.get("partial_code", False)
            for v in tool_output.values()
            if isinstance(v, dict)
        )
        partial_notice = (
            "\n> NOTE: The tools ran on a diff snippet (partial code), not the full file. "
            "Any tool errors about syntax, imports, or undefined names are ARTIFACTS of "
            "incomplete code — treat them as empty tool output.\n"
            if partial else ""
        )
        tool_summary = json.dumps(tool_output, indent=2)
        return f"""Please review the following diff for {self.domain} issues.
{partial_notice}
## Deterministic Tool Output
{tool_summary}

## Diff
```diff
{diff}
```

Analyse the diff in light of the tool output above and produce your findings.
Every finding must cite the tool output or a specific diff line as evidence.
"""

    async def review(self, diff: str, tool_output: dict) -> dict:
        with tracer.start_as_current_span(self.span_name) as span:
            start = time.monotonic()
            span.set_attribute("subagent.domain", self.domain)
            span.set_attribute("diff.length", len(diff))

            response = self.client.messages.create(
                model=_MODEL,
                max_tokens=4096,
                system=self._build_system_prompt(),
                tools=[_VERDICT_SCHEMA],
                tool_choice={"type": "tool", "name": "subagent_verdict"},
                messages=[
                    {"role": "user", "content": self._build_user_message(diff, tool_output)}
                ],
            )

            elapsed = time.monotonic() - start
            span.set_attribute("subagent.elapsed_ms", int(elapsed * 1000))
            span.set_attribute("subagent.input_tokens", response.usage.input_tokens)
            span.set_attribute("subagent.output_tokens", response.usage.output_tokens)

            # Extract the tool_use block
            for block in response.content:
                if block.type == "tool_use" and block.name == "subagent_verdict":
                    verdict = block.input
                    span.set_attribute("subagent.findings", len(verdict.get("findings", [])))
                    return verdict

            # Fallback: empty verdict
            return {"domain": self.domain, "findings": [], "summary": "No findings."}
