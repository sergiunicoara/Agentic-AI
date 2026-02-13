from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass
class EvalCase:
    id: str
    user_message: str
    expected_role: Optional[str] = None
    expected_criteria: Optional[List[str]] = None


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    score: float
    label: str
    reasoning: str
    raw: Dict[str, Any]


DEFAULT_EVAL_CASES: List[EvalCase] = [
    EvalCase(
        id="ml_senior_rag",
        user_message="I'm a hiring manager looking for a senior ML engineer who has shipped RAG systems to production.",
        expected_role="senior ml engineer",
        expected_criteria=["production", "rag"],
    ),
    EvalCase(
        id="ai_engineer_leadership",
        user_message="I need an AI engineer with leadership experience who can own LLM agents in prod.",
        expected_role="ai engineer",
        expected_criteria=["leadership", "agents", "production"],
    ),
]


def run_eval_suite(
    base_url: str,
    session_id: str = "eval-session",
    cases: Optional[List[EvalCase]] = None,
) -> List[EvalResult]:
    """Run a small behavioral evaluation suite against the /chat endpoint.

    This is intentionally simple and HTTP-based so it can be wired into a CI
    pipeline or run manually before deployments.
    """
    cases = cases or DEFAULT_EVAL_CASES
    results: List[EvalResult] = []

    for case in cases:
        chat_resp = requests.post(
            f"{base_url.rstrip('/')}/chat",
            json={"session_id": session_id, "message": case.user_message},
            timeout=60,
        )
        chat_resp.raise_for_status()
        data = chat_resp.json()
        reply = data["reply"]

        # Ask the built-in judge to evaluate this behavior via /a2a/recruiter
        judge_resp = requests.post(
            f"{base_url.rstrip('/')}/mcp/call",
            json={
                "tool": "judge_recruiter_turn",
                "arguments": {
                    "role": case.expected_role,
                    "criteria": case.expected_criteria or [],
                    "user_message": case.user_message,
                    "agent_reply": reply,
                },
            },
            timeout=60,
        )
        judge_resp.raise_for_status()
        judge_data = judge_resp.json()["result"]
        score = float(judge_data.get("score", 0.0))
        label = str(judge_data.get("label", "unknown"))
        reasoning = str(judge_data.get("reasoning", ""))

        passed = score >= 0.7

        results.append(
            EvalResult(
                case_id=case.id,
                passed=passed,
                score=score,
                label=label,
                reasoning=reasoning,
                raw={"chat": data, "judge": judge_data},
            )
        )

    return results


def results_to_json(results: List[EvalResult]) -> str:
    return json.dumps(
        [r.__dict__ for r in results],
        ensure_ascii=False,
        indent=2,
    )
