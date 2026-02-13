from __future__ import annotations

from typing import Any, Dict, List

from .cv_rag import get_cv_rag
from .tools import (
    get_all_projects,
    select_best_projects_for_role,
    generate_ats_summary_and_email,
)
from .judge import evaluate_agent_turn


# ---------------------------------------------------------------------------
# Minimal MCP-style tool registry
# ---------------------------------------------------------------------------

MCP_TOOLS: Dict[str, Dict[str, Any]] = {
    "cv_rag_query": {
        "description": "Ask a question about the candidate CV using RAG.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Natural language question."}
            },
            "required": ["question"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
            },
            "required": ["answer"],
        },
    },
    "best_projects_for_role": {
        "description": "Return the best portfolio projects for a target role and criteria.",
        "input_schema": {
            "type": "object",
            "properties": {
                "role": {"type": "string"},
                "criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Up to 3 short criteria keywords.",
                },
            },
            "required": ["role"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "projects": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["projects"],
        },
    },
    "ats_summary_and_email": {
        "description": "Generate an ATS-style summary and recruiter outreach email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "role": {"type": "string"},
                "criteria": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["role", "criteria"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "ats": {"type": "string"},
                "email": {"type": "string"},
            },
            "required": ["ats", "email"],
        },
    },
    "judge_recruiter_turn": {
        "description": "Run the LLM judge over a recruiter-agent turn.",
        "input_schema": {
            "type": "object",
            "properties": {
                "role": {"type": "string"},
                "criteria": {"type": "array", "items": {"type": "string"}},
                "user_message": {"type": "string"},
                "agent_reply": {"type": "string"},
            },
            "required": ["user_message", "agent_reply"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "label": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["score", "label"],
        },
    },
}


def list_mcp_tools() -> List[Dict[str, Any]]:
    """Return a list of MCP-style tool specs."""
    out: List[Dict[str, Any]] = []
    for name, spec in MCP_TOOLS.items():
        out.append({"name": name, **spec})
    return out


def call_mcp_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a tool call in a simple MCP-inspired way.

    This is *not* a full MCP server implementation, but it models the same
    concepts: named tools with JSON-schema parameters and structured results.
    """
    if name == "cv_rag_query":
        question = arguments.get("question", "")
        rag = get_cv_rag()
        answer = rag.query(question)
        return {"answer": str(answer)}

    if name == "best_projects_for_role":
        role = arguments.get("role", "")
        criteria = arguments.get("criteria") or []
        projects = select_best_projects_for_role(role, criteria)
        return {"projects": projects}

    if name == "ats_summary_and_email":
        role = arguments.get("role", "")
        criteria = arguments.get("criteria") or []
        projects = select_best_projects_for_role(role, criteria)
        out = generate_ats_summary_and_email(role, criteria, projects)
        return {"ats": out.get("ats", ""), "email": out.get("email", "")}

    if name == "judge_recruiter_turn":
        judge = evaluate_agent_turn(
            role=arguments.get("role"),
            criteria=arguments.get("criteria") or [],
            user_message=arguments.get("user_message", ""),
            agent_reply=arguments.get("agent_reply", ""),
        )
        return {
            "score": judge.get("score"),
            "label": judge.get("label"),
            "reasoning": judge.get("reasoning"),
        }

    raise KeyError(f"Unknown MCP tool: {name!r}")
