"""
CCA-F D1.3 + D2.5: Log Analysis Subagent
Demonstrates: built-in tools (Grep, Read, Bash), explicit context receiving.
"""
from __future__ import annotations
import logging
from agents.loop import run_agentic_loop

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Log Analysis Agent. Your sole job: parse log files
and correlate events to identify patterns relevant to the incident.

Use Grep to search for error patterns, Read to examine specific files.
Record timestamps, error rates, and sequences — not interpretations.
Return raw findings with exact log lines as evidence."""


class LogAnalysisAgent:
    async def run(self, context: dict) -> dict:
        """
        D1.3: Uses only what was passed explicitly in context.
        D2.5: Uses built-in tools (Grep, Glob, Read) for codebase exploration.
        """
        ticket_content = context["ticket_content"]
        scope = context.get("scope", {})
        log_paths = scope.get("log_paths", ["logs/"])

        query = f"""Analyze logs for this incident:
{ticket_content}

Log locations: {log_paths}
Time range: {scope.get('time_range', 'last 1 hour')}

Steps:
1. Use Glob to find relevant log files
2. Use Grep to search for error patterns
3. Use Read to examine specific log sections
4. Return findings with exact timestamps and line numbers"""

        tools = [
            {
                "name": "grep_logs",
                "description": "Search log files for a pattern. Returns matching lines with file path and line number.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path": {"type": "string", "default": "logs/"},
                    },
                    "required": ["pattern"],
                }
            },
            {
                "name": "read_log_section",
                "description": "Read a specific line range from a log file. Returns raw log lines.",
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
            tool_executor=_execute_log_tool,
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
        )

        return {
            "agent": "log_analysis",
            "status": result["status"],
            "findings": [{"fact": result.get("content", ""), "source": "log_files"}],
        }


def _execute_log_tool(tool_name: str, tool_input: dict) -> dict:
    if tool_name == "grep_logs":
        return {"matches": [], "count": 0}
    if tool_name == "read_log_section":
        return {"lines": []}
    return {"error": "unknown tool"}
