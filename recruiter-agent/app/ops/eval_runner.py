from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

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
        # --- Step 1: call the agent ---
        chat_resp = requests.post(
            f"{base_url.rstrip('/')}/chat",
            json={"session_id": session_id, "message": case.user_message},
            timeout=60,
        )
        chat_resp.raise_for_status()
        data = chat_resp.json()
        reply = data["reply"]

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

        passed = score >= 3.5  # pass threshold: 3.5 / 5

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
