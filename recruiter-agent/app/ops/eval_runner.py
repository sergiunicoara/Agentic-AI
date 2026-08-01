from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from ..utils.normalize import normalize_criteria

# ---------------------------------------------------------------------------
# Golden dataset path — ops/eval_data.json
# ---------------------------------------------------------------------------
EVAL_DATA_PATH = Path(__file__).parent.parent.parent / "ops" / "eval_data.json"


@dataclass
class EvalCase:
    id: str
    user_message: str
    expected_role: Optional[str] = None
    expected_criteria: Optional[List[str]] = None
    description: str = ""
    setup_messages: List[str] = field(default_factory=list)


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    score: float
    faithfulness: float
    relevancy: float
    factuality: float
    label: str
    reasoning: str
    expected_state_passed: bool = True
    state_issues: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Load golden dataset
# ---------------------------------------------------------------------------

def load_eval_cases(path: Path = EVAL_DATA_PATH) -> List[EvalCase]:
    """Load evaluation cases from the golden dataset JSON file."""
    if not path.exists():
        return _DEFAULT_EVAL_CASES

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return [
        EvalCase(
            id=item["id"],
            user_message=item["user_message"],
            expected_role=item.get("expected_role"),
            expected_criteria=item.get("expected_criteria"),
            description=item.get("description", ""),
            setup_messages=item.get("setup_messages", []),
        )
        for item in data
    ]


# Fallback if file is missing
_DEFAULT_EVAL_CASES: List[EvalCase] = [
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


def _internal_headers() -> Dict[str, str]:
    """Authenticate eval calls to protected MCP/A2A endpoints when configured."""
    key = os.environ.get("INTERNAL_API_KEY", "").strip()
    return {"X-Internal-Api-Key": key} if key else {}


def _state_issues(case: EvalCase, state: Any) -> List[str]:
    """Make expected role/criteria executable golden assertions."""
    if not isinstance(state, dict):
        return ["missing response state"] if (case.expected_role or case.expected_criteria is not None) else []

    issues: List[str] = []
    if case.expected_role:
        actual_role = str(state.get("role") or "").casefold()
        if actual_role != case.expected_role.casefold():
            issues.append(f"role expected {case.expected_role!r}, got {state.get('role')!r}")

    if case.expected_criteria is not None:
        expected = sorted(normalize_criteria(case.expected_criteria))
        actual = sorted(normalize_criteria(state.get("criteria") or []))
        if actual != expected:
            issues.append(f"criteria expected {expected!r}, got {actual!r}")

    return issues


# ---------------------------------------------------------------------------
# Run eval suite
# ---------------------------------------------------------------------------

def run_eval_suite(
    base_url: str,
    session_id: str = "eval-session",
    cases: Optional[List[EvalCase]] = None,
) -> List[EvalResult]:
    """
    Run the full evaluation suite against the live /chat + /mcp/call endpoints.

    For each golden case:
      1. Sends the user_message to /chat
      2. Routes the reply + expected context to /mcp/call → judge_recruiter_turn
      3. Records faithfulness, relevancy, factuality, and overall score
    """
    cases = cases or load_eval_cases()
    results: List[EvalResult] = []

    for case in cases:
        # Each case gets its own isolated session so state never bleeds between cases
        case_session_id = f"{session_id}-{case.id}"

        # --- Step 0: send any setup messages to prime session context ---
        for setup_msg in case.setup_messages:
            requests.post(
                f"{base_url.rstrip('/')}/chat",
                json={"session_id": case_session_id, "message": setup_msg},
                timeout=60,
            )
            time.sleep(1)

        # --- Step 1: call the agent ---
        chat_resp = requests.post(
            f"{base_url.rstrip('/')}/chat",
            json={"session_id": case_session_id, "message": case.user_message},
            timeout=60,
        )
        chat_resp.raise_for_status()
        data = chat_resp.json()
        reply = data["reply"]
        state_issues = _state_issues(case, data.get("state"))

        # --- Step 2: judge via MCP tool endpoint ---
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
            headers=_internal_headers(),
            timeout=60,
        )
        judge_resp.raise_for_status()
        judge_data = judge_resp.json()["result"]

        score = float(judge_data.get("score", 0.0))
        faithfulness = float(judge_data.get("faithfulness", 0.0))
        relevancy = float(judge_data.get("relevancy", 0.0))
        factuality = float(judge_data.get("factuality", 0.0))
        label = str(judge_data.get("label", "unknown"))
        reasoning = str(judge_data.get("reasoning", judge_data.get("notes", "")))

        expected_state_passed = not state_issues
        passed = score >= 3.5 and expected_state_passed  # pass threshold: 3.5 / 5 + golden assertions

        results.append(
            EvalResult(
                case_id=case.id,
                passed=passed,
                score=score,
                faithfulness=faithfulness,
                relevancy=relevancy,
                factuality=factuality,
                label=label,
                reasoning=reasoning,
                expected_state_passed=expected_state_passed,
                state_issues=state_issues,
                raw={"chat": data, "judge": judge_data},
            )
        )

        # Respect free-tier rate limit: 15 RPM = 1 request every 4s
        time.sleep(5)

    return results


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------

def aggregate_metrics(results: List[EvalResult]) -> Dict[str, float]:
    """Compute aggregate scoring metrics across all eval cases."""
    if not results:
        return {}

    n = len(results)
    return {
        "n_cases": float(n),
        "pass_rate": round(sum(1 for r in results if r.passed) / n, 3),
        "avg_score": round(sum(r.score for r in results) / n, 3),
        "avg_faithfulness": round(sum(r.faithfulness for r in results) / n, 3),
        "avg_relevancy": round(sum(r.relevancy for r in results) / n, 3),
        "avg_factuality": round(sum(r.factuality for r in results) / n, 3),
    }


def results_to_json(results: List[EvalResult]) -> str:
    out = {
        "aggregate": aggregate_metrics(results),
        "results": [r.__dict__ for r in results],
    }
    return json.dumps(out, ensure_ascii=False, indent=2)
