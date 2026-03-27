"""
Layer 4: Review Agent

Operates independently of the subagents. Receives only the merged orchestrator output
(diff + tool_output + subagent_verdicts) and produces the final structured disposition.

Responsibilities:
1. Validate that every subagent finding has a traceable evidence field
2. Suppress or flag untraceable findings in the regression log
3. Produce a final ReviewDisposition: approve | request_changes | comment
4. Rank findings by severity and annotate with line numbers
"""
import json
import os
import time
from pathlib import Path

import anthropic

from observability.tracer import get_tracer

_MODEL = os.getenv("REVIEW_MODEL", "claude-opus-4-6")

tracer = get_tracer("review_agent")

_DISPOSITION_SCHEMA = {
    "name": "review_disposition",
    "description": "Final structured code review disposition with ranked, line-level annotations",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["approve", "request_changes", "comment"],
                "description": (
                    "approve: no blocking issues found. "
                    "request_changes: one or more error-severity findings require resolution. "
                    "comment: warnings or info only, informational review."
                ),
            },
            "findings": {
                "type": "array",
                "description": "All validated, traceable findings ranked by severity (errors first)",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "file": {"type": "string"},
                        "line": {"type": ["integer", "null"]},
                        "severity": {"type": "string", "enum": ["error", "warning", "info"]},
                        "domain": {"type": "string", "enum": ["security", "architecture", "style", "tool"]},
                        "rule": {"type": "string"},
                        "message": {"type": "string"},
                        "evidence": {"type": "string"},
                        "suggestion": {
                            "type": "string",
                            "description": "Optional concrete fix suggestion",
                        },
                    },
                    "required": ["id", "file", "severity", "domain", "rule", "message", "evidence"],
                },
            },
            "suppressed_count": {
                "type": "integer",
                "description": "Number of subagent findings suppressed due to missing evidence",
            },
            "summary": {
                "type": "string",
                "description": "One-paragraph review summary suitable for a PR comment",
            },
        },
        "required": ["verdict", "findings", "suppressed_count", "summary"],
    },
}

_SYSTEM_PROMPT = """You are the final, authoritative code review agent. You operate independently
of the specialised subagents. Your job is to:

1. VALIDATE TRACEABILITY: For each subagent finding, verify it has a non-empty `evidence` field
   that quotes either tool output or a specific diff line. Suppress findings that fail this check
   and count them in `suppressed_count`.

2. MERGE AND DEDUPLICATE: Combine findings from all subagents and tool output. Remove exact
   duplicates or findings that are already captured by a tool result.

3. RANK: Order findings by severity (errors → warnings → info). Within the same severity,
   order by potential impact.

4. VERDICT:
   - `request_changes` if any error-severity finding survives traceability validation
   - `comment` if only warnings or info findings remain
   - `approve` if no findings survive validation

5. SUMMARY: Write a concise one-paragraph summary suitable for a pull request comment.
   Reference specific files and lines. Be direct and actionable.

You MUST call the `review_disposition` tool with your output. Do not produce prose outside
the tool call.
"""


class ReviewAgent:
    """Final review agent — validates traceability and produces the authoritative disposition."""

    def __init__(self):
        self.client = anthropic.Anthropic()

    async def review(self, orchestrator_output: dict) -> dict:
        """
        Produce the final ReviewDisposition from the orchestrator's merged output.
        """
        with tracer.start_as_current_span("review_agent.review") as span:
            start = time.monotonic()

            diff = orchestrator_output.get("diff", "")
            tool_output = orchestrator_output.get("tool_output", {})
            subagent_verdicts = orchestrator_output.get("subagent_verdicts", {})
            skills_used = orchestrator_output.get("skills_used", [])

            span.set_attribute("review.skills_used", len(skills_used))
            span.set_attribute(
                "review.subagent_findings_total",
                sum(
                    len(v.get("findings", []))
                    for v in subagent_verdicts.values()
                ),
            )

            user_message = self._build_user_message(diff, tool_output, subagent_verdicts)

            response = self.client.messages.create(
                model=_MODEL,
                max_tokens=8192,
                system=_SYSTEM_PROMPT,
                tools=[_DISPOSITION_SCHEMA],
                tool_choice={"type": "tool", "name": "review_disposition"},
                messages=[{"role": "user", "content": user_message}],
            )

            elapsed = time.monotonic() - start
            span.set_attribute("review_agent.elapsed_ms", int(elapsed * 1000))
            span.set_attribute("review_agent.input_tokens", response.usage.input_tokens)
            span.set_attribute("review_agent.output_tokens", response.usage.output_tokens)

            for block in response.content:
                if block.type == "tool_use" and block.name == "review_disposition":
                    disposition = block.input
                    span.set_attribute("review.verdict", disposition.get("verdict", "unknown"))
                    span.set_attribute(
                        "review.findings_count", len(disposition.get("findings", []))
                    )
                    span.set_attribute(
                        "review.suppressed_count", disposition.get("suppressed_count", 0)
                    )

                    # Log suppressed findings to regression log
                    if disposition.get("suppressed_count", 0) > 0:
                        self._log_suppressed(disposition, orchestrator_output)

                    return disposition

            return {
                "verdict": "comment",
                "findings": [],
                "suppressed_count": 0,
                "summary": "Review agent produced no output.",
            }

    def _build_user_message(
        self, diff: str, tool_output: dict, subagent_verdicts: dict
    ) -> str:
        return f"""Please review the following code change and produce the final disposition.

## Tool Output (Deterministic)
```json
{json.dumps(tool_output, indent=2)}
```

## Subagent Verdicts
```json
{json.dumps(subagent_verdicts, indent=2)}
```

## Original Diff
```diff
{diff}
```

Validate traceability, merge findings, rank by severity, and produce the review_disposition.
"""

    def _log_suppressed(self, disposition: dict, orchestrator_output: dict) -> None:
        """Append suppressed-finding events to the regression log."""
        import json as _json
        log_path = Path(__file__).parent.parent / "eval" / "regression_log.jsonl"
        log_path.parent.mkdir(exist_ok=True)
        entry = {
            "event": "suppressed_findings",
            "suppressed_count": disposition.get("suppressed_count", 0),
            "verdict": disposition.get("verdict"),
            "skills_used": orchestrator_output.get("skills_used", []),
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(entry) + "\n")
