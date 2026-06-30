"""SearchAgent: web search specialist."""
from __future__ import annotations

from typing import Optional

from app.agents.base import BaseHermesAgent
from app.observability import RequestMetrics
from app.tools import web_search

_SYSTEM = """You are a web research specialist. Your job is to find accurate, up-to-date information
on the given topic using web search. Always search multiple angles of the question.
Summarize findings with source URLs. Be concise and factual."""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information on a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "max_results": {"type": "integer", "description": "Max results to return (1-10)", "default": 5},
                },
                "required": ["query"],
            },
        },
    }
]


def make_search_agent(metrics: Optional[RequestMetrics] = None) -> BaseHermesAgent:
    return BaseHermesAgent(
        agent_id="search_agent",
        system_prompt=_SYSTEM,
        tools=_TOOLS,
        tool_handlers={"web_search": web_search},
        metrics=metrics,
    )
