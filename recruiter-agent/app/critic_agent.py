"""
app/critic_agent.py — Autonomous Critic Agent (A2A Validator)

Implements the critic side of the Agent-to-Agent (A2A) interoperability layer.

Role:
  - Receives completed recruiter-agent turns via the MCP tool interface
  - Calls `judge_recruiter_turn` through `call_mcp_tool` (structured A2A handoff)
  - Interprets multi-metric scores (faithfulness, relevancy, factuality)
  - Issues a PASS / FAIL verdict with concrete recommended actions
  - Maintains a per-session validation log for aggregate reporting

This agent runs as a separate logical process invoked via /a2a/validate,
making the recruiter ↔ critic interaction a genuine Agent-to-Agent exchange.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .mcp import call_mcp_tool

logger = logging.getLogger(__name__)

# Minimum overall score (1–5 scale) to issue a PASS verdict
_PASS_THRESHOLD = 3.5


# ---------------------------------------------------------------------------
# Critic session state
# ---------------------------------------------------------------------------

class CriticState:
    """
    Lightweight per-session memory for the critic agent.
    Tracks all validation results and computes running aggregate metrics.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.validations: List[Dict[str, Any]] = []

    def record(self, result: Dict[str, Any]) -> None:
        self.validations.append(result)

    def aggregate(self) -> Dict[str, Any]:
        n = len(self.validations)
        if not n:
            return {"n_validations": 0}

        passed = sum(1 for v in self.validations if v.get("passed"))
        return {
            "n_validations": n,
            "pass_rate": round(passed / n, 3),
            "avg_score": round(
                sum(v.get("score", 0) for v in self.validations) / n, 3
            ),
            "avg_faithfulness": round(
                sum(v.get("faithfulness", 0) for v in self.validations) / n, 3
            ),
            "avg_relevancy": round(
                sum(v.get("relevancy", 0) for v in self.validations) / n, 3
            ),
            "avg_factuality": round(
                sum(v.get("factuality", 0) for v in self.validations) / n, 3
            ),
        }


# In-memory critic sessions keyed by session_id
_critic_sessions: Dict[str, CriticState] = {}


def _get_critic_state(session_id: str) -> CriticState:
    if session_id not in _critic_sessions:
        _critic_sessions[session_id] = CriticState(session_id)
    return _critic_sessions[session_id]


# ---------------------------------------------------------------------------
# Recommended actions
# ---------------------------------------------------------------------------

def _recommended_actions(score: float, issues: List[str]) -> List[str]:
    """
    Map score + issue labels to concrete next-step recommendations.
    This is the critic agent's "reasoning output" — not just a score, but a decision.
    """
    issues_text = " ".join(issues).lower()
    actions: List[str] = []

    if score < 2.5:
        actions.append(
            "ESCALATE: reply quality is critically low — regenerate before delivery"
        )
    elif score < _PASS_THRESHOLD:
        actions.append(
            "REVIEW: reply did not meet quality threshold — consider refining response"
        )

    if "hallucination" in issues_text or "fabricat" in issues_text:
        actions.append(
            "GROUND: inject verified CV context to eliminate hallucinated claims"
        )
    if "off_topic" in issues_text or "irrelevant" in issues_text:
        actions.append(
            "RE-ROUTE: user intent not matched — clarify pipeline stage and retry"
        )
    if "judge_unavailable" in issues_text or "judge_call_error" in issues_text:
        actions.append(
            "DEGRADE: judge unavailable — validation skipped, flagging for manual review"
        )

    if not actions:
        actions.append(
            "PASS: reply meets quality standards — continue recruiter session"
        )

    return actions


# ---------------------------------------------------------------------------
# Core critic agent logic
# ---------------------------------------------------------------------------

def validate_turn(
    user_message: str,
    agent_reply: str,
    role: Optional[str] = None,
    criteria: Optional[List[str]] = None,
    session_id: str = "default",
) -> Dict[str, Any]:
    """
    Critic agent entry point.

    Performs an A2A call to the judge via the MCP tool interface,
    interprets multi-metric scores, and returns a structured verdict
    with recommended actions and running session aggregate metrics.

    Returns:
        {
            "verdict":              "PASS" | "FAIL",
            "passed":               bool,
            "score":                float,          # 1–5
            "faithfulness":         float,          # 0.0–1.0
            "relevancy":            float,          # 0.0–1.0
            "factuality":           float,          # 0.0–1.0
            "label":                str,
            "issues":               List[str],
            "reasoning":            str,
            "recommended_actions":  List[str],
            "session_aggregate":    Dict[str, Any],
        }
    """
    critic_state = _get_critic_state(session_id)

    # --- A2A handoff: call judge tool via MCP interface ---
    try:
        judge_result = call_mcp_tool(
            "judge_recruiter_turn",
            {
                "role": role,
                "criteria": criteria or [],
                "user_message": user_message,
                "agent_reply": agent_reply,
            },
        )
    except Exception as exc:
        logger.warning("Critic agent: judge MCP call failed — %s", exc)
        judge_result = {
            "score": 3.0,
            "faithfulness": 0.5,
            "relevancy": 0.5,
            "factuality": 0.5,
            "label": "mixed",
            "issues": ["judge_unavailable"],
            "reasoning": str(exc),
        }

    score = float(judge_result.get("score", 3.0))
    passed = score >= _PASS_THRESHOLD
    issues: List[str] = judge_result.get("issues") or []

    validation: Dict[str, Any] = {
        "session_id": session_id,
        "verdict": "PASS" if passed else "FAIL",
        "passed": passed,
        "score": score,
        "faithfulness": float(judge_result.get("faithfulness", 0.5)),
        "relevancy": float(judge_result.get("relevancy", 0.5)),
        "factuality": float(judge_result.get("factuality", 0.5)),
        "label": judge_result.get("label", "mixed"),
        "issues": issues,
        "reasoning": judge_result.get("reasoning", ""),
        "recommended_actions": _recommended_actions(score, issues),
        "session_aggregate": critic_state.aggregate(),
    }

    critic_state.record(validation)

    logger.info(
        "critic_agent | session=%s verdict=%s score=%.1f "
        "faithfulness=%.2f relevancy=%.2f factuality=%.2f",
        session_id,
        validation["verdict"],
        score,
        validation["faithfulness"],
        validation["relevancy"],
        validation["factuality"],
    )

    return validation


def get_critic_session_summary(session_id: str) -> Dict[str, Any]:
    """Return aggregate validation metrics for a given critic session."""
    state = _critic_sessions.get(session_id)
    if state is None:
        return {"session_id": session_id, "n_validations": 0}
    return {"session_id": session_id, **state.aggregate()}
