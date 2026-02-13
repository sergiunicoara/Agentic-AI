"""
Evaluation Script for the Recruiter Agent
-----------------------------------------

Runs golden conversations against the deployed agent and collects:

- LLM-judge scores
- Issue distribution
- Score statistics
- Per-conversation breakdown

This implements a simple "Evaluation as a Quality Gate"
step from the Google Agents course.

Run:
    python eval_agent.py
"""

import json
import time
import requests
from dataclasses import dataclass, field
from typing import List, Dict, Any

# -----------------------------
# CONFIG
# -----------------------------
BACKEND = "https://recruiter-agent-190861422358.europe-west1.run.app"   # <-- change this
SESSION_STORE = "http://localhost:8000/admin/session"  # optional local session debug


# -----------------------------
# Golden conversations
# -----------------------------
@dataclass
class TestCase:
    name: str
    turns: List[str]  # sequential messages
    expected_role: str = ""
    expected_criteria: List[str] = field(default_factory=list)


GOLDEN_SET = [
    TestCase(
        name="ML Engineer basic",
        turns=[
            "Senior ML Engineer",
            "ownership, production RAG",
            "1",
            "another",
            "2"
        ],
        expected_role="Senior Ml Engineer",
        expected_criteria=["ownership", "production_rag"]
    ),
    TestCase(
        name="JD-first flow",
        turns=[
            """About the role
            Responsibilities:
            - Build ML pipelines
            - Own end-to-end systems
            Requirements: leadership, communication
            """,
            "Senior ML Engineer",
            "ownership, leadership",
            "1",
            "2"
        ]
    ),
]


# -----------------------------
# Helpers
# -----------------------------
def call_chat(session_id: str, message: str) -> Dict[str, Any]:
    payload = {
        "session_id": session_id,
        "message": message,
    }
    resp = requests.post(BACKEND, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_judge_scores(state: Dict[str, Any]) -> List[int]:
    """
    Pull all LLM-judge scores from trajectory JSON.
    """
    scores = []
    for step in state.get("trajectory", {}).get("steps", []):
        if step.get("kind") == "tool" and step.get("message") == "llm_judge_evaluation":
            meta = step.get("meta", {})
            score = meta.get("score")
            if isinstance(score, (int, float)):
                scores.append(score)
    return scores


def load_session_state(session_id: str) -> Dict[str, Any]:
    """
    Assuming server stores sessions in /tmp/sqlite,
    expose a debug endpoint OR use a file reader.

    If you don't expose state, remove this and instead
    modify server.py to return judge score in /chat responses.
    """
    # If you haven't built an admin endpoint, this will need adjustment.
    # For now assume you did: GET /admin/session/<id>
    url = f"{SESSION_STORE}/{session_id}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


# -----------------------------
# Main evaluation runner
# -----------------------------
def run_eval():
    print("\n=== Recruiter Agent Evaluation ===\n")
    all_scores = []
    issue_counts: Dict[str, int] = {}
    report = []

    for test in GOLDEN_SET:
        session_id = f"eval-{int(time.time()*1000)}"
        print(f"Running: {test.name}  (session_id={session_id})")

        for turn in test.turns:
            out = call_chat(session_id, turn)
            # Let agent process + store session
            time.sleep(0.2)

        # Load session trajectory
        state = load_session_state(session_id)
        scores = extract_judge_scores(state)
        if scores:
            all_scores.extend(scores)

        # Track issues
        for step in state.get("trajectory", {}).get("steps", []):
            if step.get("message") == "llm_judge_evaluation":
                issues = step.get("meta", {}).get("issues", [])
                for issue in issues:
                    issue_counts[issue] = issue_counts.get(issue, 0) + 1

        report.append({
            "test": test.name,
            "scores": scores,
            "avg_score": sum(scores)/len(scores) if scores else None
        })

    # -----------------------------
    # Results summary
    # -----------------------------
    print("\n=== Scores Summary ===")
    if all_scores:
        avg = sum(all_scores)/len(all_scores)
        best = max(all_scores)
        worst = min(all_scores)
        print(f"Overall avg score: {avg:.2f}")
        print(f"Best score: {best}")
        print(f"Worst score: {worst}")
    else:
        print("No LLM-judge scores found.")

    print("\n=== Issue Distribution ===")
    for issue, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
        print(f"{issue}: {count}")

    print("\n=== Per-Conversation Breakdown ===")
    for entry in report:
        print(json.dumps(entry, indent=2))

    print("\nEvaluation complete.\n")


if __name__ == "__main__":
    run_eval()
