"""SynthesisAgent: compiles worker outputs into a final cited report."""
from __future__ import annotations

from typing import Optional

from app.agents.base import BaseHermesAgent
from app.observability import RequestMetrics

_SYSTEM = """You are a research synthesis specialist. Given collected information from web
search and knowledge base retrieval, write a comprehensive, well-structured research report.

Report format:
## Executive Summary
(2-3 sentences)

## Key Findings
(bullet points, each with a [Source: URL or doc_id] citation)

## Analysis
(deeper analysis of the findings)

## Conclusion
(concise conclusion)

## References
(numbered list of all sources cited)

Be factual. If information is uncertain, say so. Do NOT call any tools. Write the report directly."""


def make_synthesis_agent(metrics: Optional[RequestMetrics] = None) -> BaseHermesAgent:
    return BaseHermesAgent(
        agent_id="synthesis_agent",
        system_prompt=_SYSTEM,
        tools=[],
        tool_handlers={},
        metrics=metrics,
        token_budget=8000,
    )
