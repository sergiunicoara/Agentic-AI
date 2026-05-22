"""
CCA-F D1.3 + D5.4: Code Analysis Subagent
D5.4: Large codebase exploration — subagent delegation, key finding summarization,
context degradation management in extended sessions.
"""
from __future__ import annotations
import logging
from agents.loop import run_agentic_loop

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Code Analysis Agent for incident investigation.
Your job: inspect repository code to identify the root cause at the code level.

Strategy for large codebases (D5.4 exam concept):
1. Start with entry points, not full file reads (context degradation risk)
2. Use Grep to pinpoint relevant files before reading them
3. Read only targeted sections, not entire files
4. Summarize key findings incrementally — do NOT accumulate full file contents
5. Use scratchpad to track what you've learned: <scratchpad>findings so far</scratchpad>

Avoid: reading every file (context bloat), losing key findings in long sessions."""


class CodeAnalysisAgent:
    async def run(self, context: dict) -> dict:
        """D5.4: Delegates large codebase exploration; uses incremental summarization."""
        ticket_content = context["ticket_content"]
        scope = context.get("scope", {})
        repo_path = scope.get("repo_path", ".")
        service = scope.get("service_name", "")

        query = f"""Investigate code-level root cause for:
{ticket_content}

Repository: {repo_path}
Service/component: {service}

Start by grepping for error messages from the ticket, then trace code paths.
Use your scratchpad to record findings before context gets large."""

        tools = [
            {
                "name": "grep_codebase",
                "description": "Search source code files by regex pattern. Returns file paths and matching lines with context.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "file_glob": {"type": "string", "default": "**/*.py"},
                        "context_lines": {"type": "integer", "default": 3},
                    },
                    "required": ["pattern"],
                }
            },
            {
                "name": "read_file_section",
                "description": "Read specific line range of a source file. Use targeted ranges, not full files.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                    },
                    "required": ["file_path", "start_line", "end_line"],
                }
            },
        ]

        result = run_agentic_loop(
            system_prompt=SYSTEM_PROMPT,
            initial_message=query,
            tools=tools,
            tool_executor=_execute_code_tool,
            model="claude-sonnet-4-6",  # code analysis needs sonnet
            max_tokens=4096,
        )

        return {
            "agent": "code_analysis",
            "status": result["status"],
            "findings": [{"fact": result.get("content", ""), "source": f"repository:{repo_path}"}],
        }


def _execute_code_tool(tool_name: str, tool_input: dict) -> dict:
    if tool_name == "grep_codebase":
        return {"matches": [], "count": 0}
    if tool_name == "read_file_section":
        return {"lines": []}
    return {"error": "unknown tool"}
