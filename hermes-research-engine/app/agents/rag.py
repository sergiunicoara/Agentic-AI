"""RAGAgent: retrieves from the persistent knowledge base."""
from __future__ import annotations

from typing import Optional

from app.agents.base import BaseHermesAgent
from app.observability import RequestMetrics
from app.tools import retrieve_knowledge

_SYSTEM = """You are a knowledge retrieval specialist. Call retrieve_knowledge ONCE with the given topic.
If results are returned, summarize the key points. If the results are empty or irrelevant, respond:
"No relevant knowledge found in the knowledge base."
Do NOT call the tool more than once. Do NOT ingest documents."""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_knowledge",
            "description": "Semantic search over the persistent knowledge base. Call this ONCE.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "k": {"type": "integer", "description": "Number of results (1-5)", "default": 3},
                },
                "required": ["query"],
            },
        },
    },
]


def make_rag_agent(metrics: Optional[RequestMetrics] = None) -> BaseHermesAgent:
    return BaseHermesAgent(
        agent_id="rag_agent",
        system_prompt=_SYSTEM,
        tools=_TOOLS,
        tool_handlers={"retrieve_knowledge": retrieve_knowledge},
        metrics=metrics,
        token_budget=4000,
    )
