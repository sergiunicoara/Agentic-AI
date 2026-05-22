"""
CCA-F D1.3: Subagent Configuration — Retrieval Agent
Demonstrates: explicit context receiving, isolated memory, goal-oriented prompting.

Exam trap: subagents must NOT assume they inherit coordinator context.
Every piece of info needed must be passed explicitly in the context dict.
"""
from __future__ import annotations
import logging
import anthropic
from agents.loop import run_agentic_loop
from agents.provenance import ProvenanceTracker, SourceRef

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a specialized Retrieval Agent for incident investigation.
Your ONLY job: search documentation, runbooks, and knowledge base to find context
relevant to the incident described. You do not analyze logs or code.

When you find relevant information:
1. Record the source (document name, URL, or DB record ID)
2. Note the exact fact extracted
3. Rate relevance 0.0-1.0

Use the available tools to search. Return ALL findings, even partial matches."""


class RetrievalAgent:
    """
    Isolated subagent — receives context explicitly, returns findings with provenance.
    D1.3: Structured handoff format — output feeds directly into coordinator.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()

    async def run(self, context: dict) -> dict:
        """
        context must contain (D1.3 — explicit, not assumed):
        - task_id: str
        - ticket_content: str
        - scope: dict (keywords, time_range, etc.)
        - provenance_tracker: ProvenanceTracker
        """
        ticket_content = context["ticket_content"]
        scope = context.get("scope", {})
        keywords = scope.get("keywords", [])
        provenance: ProvenanceTracker = context.get("provenance_tracker")

        # Build scoped query — don't pass entire coordinator history
        query = f"""Ticket: {ticket_content}

Search for documentation, runbooks, or past incidents related to:
Keywords: {', '.join(keywords) if keywords else 'auto-detect from ticket'}
Time range: {scope.get('time_range', 'last 90 days')}

Return structured findings."""

        tools = _retrieval_tools()

        result = run_agentic_loop(
            system_prompt=SYSTEM_PROMPT,
            initial_message=query,
            tools=tools,
            tool_executor=_execute_retrieval_tool,
            model="claude-haiku-4-5-20251001",  # retrieval is cheap
            max_tokens=2048,
        )

        # Register provenance for every finding (D5.6)
        findings = _parse_findings(result.get("content", ""))
        if provenance:
            for f in findings:
                provenance.add(SourceRef(
                    fact=f["fact"],
                    source=f["source"],
                    agent="retrieval",
                    confidence=f.get("relevance", 0.8),
                ))

        return {
            "agent": "retrieval",
            "status": result["status"],
            "findings": findings,
            "iterations": result.get("iterations", 0),
        }


def _retrieval_tools() -> list[dict]:
    """
    D2.1: Tool descriptions follow VERB + NOUN + BOUNDARY + CONSTRAINTS.
    Compare to bad versions in anti_patterns/01_vague_tool_descriptions.py
    """
    return [
        {
            "name": "search_knowledge_base",
            # Good: verb(search) + noun(knowledge base articles) + boundary(by keyword) + constraint(top N)
            "description": "Search knowledge base articles by keyword. Returns top 10 most relevant articles with title, URL, and excerpt.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query keywords"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
        {
            "name": "lookup_past_incidents",
            # Good: precise boundary (resolved incidents), constraint (same service)
            "description": "Look up resolved past incidents for a given service name. Returns incident summaries with root causes, within the last 90 days.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string"},
                    "days_back": {"type": "integer", "default": 90},
                },
                "required": ["service_name"],
            },
        },
    ]


def _execute_retrieval_tool(tool_name: str, tool_input: dict) -> dict:
    """Tool executor — in production wires to real MCP server."""
    if tool_name == "search_knowledge_base":
        # Mock — replace with mcp__filesystem or mcp__postgres call
        return {"results": [{"title": "Example runbook", "excerpt": "...", "url": "/docs/runbook-1"}]}
    if tool_name == "lookup_past_incidents":
        return {"incidents": []}
    return {"error": "unknown tool"}


def _parse_findings(content: str) -> list[dict]:
    """Extract structured findings from agent text output."""
    # In production: use structured output / tool_choice forced extraction
    return [{"fact": content[:200] if content else "No findings", "source": "retrieval_agent", "relevance": 0.7}]
