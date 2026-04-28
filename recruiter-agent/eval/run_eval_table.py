"""
LLM-as-a-Judge evaluation runner
Calls /a2a/validate against golden test cases and prints a results table.
Screenshot the terminal output for portfolio / LinkedIn.

Run:
    python eval/run_eval_table.py
"""

import sys
import requests
import time

# Force UTF-8 output on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND = "https://recruiter-agent-969006882005.europe-west1.run.app"
VALIDATE = f"{BACKEND}/a2a/validate"
CHAT     = f"{BACKEND}/chat"

# ── Golden dataset ──────────────────────────────────────────────────────────

GOLDEN = [
    {
        "name": "Role extraction — voice AI",
        "user": "We're hiring a Lead AI Engineer with hands-on voice pipeline experience — STT/TTS, real-time streaming, RAG.",
        "role": "Lead AI Engineer",
        "criteria": ["voice_ai", "production_rag", "low_latency"],
        "expected_keywords": ["deepgram", "tts", "voice"],
    },
    {
        "name": "Criteria parsing — observability",
        "user": "Senior ML Engineer. We care about LLM observability, OTel tracing, and evaluation harnesses.",
        "role": "Senior ML Engineer",
        "criteria": ["observability"],
        "expected_keywords": ["otel", "observability", "tracing"],
    },
    {
        "name": "Project deep dive — RAG",
        "user": "1",
        "role": "LLM Engineer",
        "criteria": ["production_rag", "ownership"],
        "warmup": ["LLM Engineer", "production RAG, ownership"],
        "expected_keywords": ["rag", "retrieval", "ragas"],
    },
    {
        "name": "CV Q&A — certifications",
        "user": "Which certifications does Sergiu have?",
        "role": "AI Engineer",
        "criteria": ["communication"],
        "expected_keywords": ["certificate", "certification", "google", "course"],
    },
    {
        "name": "ATS summary quality",
        "user": "2",
        "role": "Senior Voice AI Engineer",
        "criteria": ["voice_ai", "production_rag", "observability"],
        "warmup": ["Senior Voice AI Engineer", "voice AI, production RAG, observability"],
        "expected_keywords": ["deepgram", "cloud run", "rag"],
    },
    {
        "name": "Shortcut without role — guard",
        "user": "1",
        "role": None,
        "criteria": [],
        "expected_keywords": ["role", "engineer"],
    },
]

# ── Run ─────────────────────────────────────────────────────────────────────

def chat_turn(session_id: str, message: str, state: dict | None = None) -> tuple[str, dict]:
    """Single chat turn. Returns (reply, new_state)."""
    payload = {"session_id": session_id, "message": message, "source": "eval", "state": state}
    try:
        r = requests.post(CHAT, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        return data.get("reply", ""), data.get("state")
    except Exception as e:
        return f"[chat error: {e}]", state


def get_agent_reply(user_msg: str, role: str | None, criteria: list, warmup: list | None = None) -> str:
    """Get a real agent reply to evaluate. warmup = prior turns to establish state."""
    session_id = f"eval-{int(time.time()*1000)}"
    state = None
    if warmup:
        for turn in warmup:
            _, state = chat_turn(session_id, turn, state)
            time.sleep(0.1)
    reply, _ = chat_turn(session_id, user_msg, state)
    return reply


def validate(user_msg: str, agent_reply: str, role: str | None, criteria: list) -> dict:
    payload = {
        "user_message": user_msg,
        "agent_reply":  agent_reply,
        "role":         role,
        "criteria":     criteria,
        "session_id":   f"eval-{int(time.time()*1000)}",
    }
    try:
        r = requests.post(VALIDATE, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"verdict": "ERROR", "score": 0, "faithfulness": 0, "relevancy": 0, "factuality": 0, "label": "error", "reasoning": str(e)}


# ── Pretty print ─────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
DIM    = "\033[2m"

def score_color(v: float, max_v: float = 1.0) -> str:
    ratio = v / max_v
    if ratio >= 0.8: return GREEN
    if ratio >= 0.6: return YELLOW
    return RED

def bar(v: float, width: int = 10) -> str:
    filled = round(v * width)
    return "#" * filled + "." * (width - filled)

def fmt_float(v: float) -> str:
    c = score_color(v)
    return f"{c}{v:.2f}{RESET}"

def fmt_score(v: float) -> str:
    c = score_color(v, max_v=5)
    return f"{c}{v:.1f}/5{RESET}"


def print_results(results: list):
    col_w = [32, 8, 11, 10, 11, 8, 9]
    headers = ["Test Case", "Score", "Faithful", "Relevant", "Factual", "Label", "Verdict"]

    sep = "-" * (sum(col_w) + len(col_w) * 3 + 1)
    print(f"\n{BOLD}{CYAN}{sep}{RESET}")
    print(f"{BOLD}{CYAN}  LLM-as-a-Judge Evaluation  |  Recruiter Agent  |  Golden Dataset{RESET}")
    print(f"{BOLD}{CYAN}{sep}{RESET}\n")

    # Header
    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, col_w))
    print(f"{BOLD}{header_row}{RESET}")
    print(sep)

    totals = {"score": [], "faithfulness": [], "relevancy": [], "factuality": [], "pass": 0}

    for r in results:
        v = r["verdict"]
        label = r.get("label", "?")
        score = r.get("score", 0)
        faith = r.get("faithfulness", 0)
        relev = r.get("relevancy", 0)
        factu = r.get("factuality", 0)
        passed = v == "PASS"

        totals["score"].append(score)
        totals["faithfulness"].append(faith)
        totals["relevancy"].append(relev)
        totals["factuality"].append(factu)
        if passed:
            totals["pass"] += 1

        verdict_str = f"{GREEN}PASS ✓{RESET}" if passed else f"{RED}FAIL ✗{RESET}"
        name = r["name"][:col_w[0]]

        row = (
            f"  {name:<{col_w[0]}}"
            f"  {fmt_score(score):<{col_w[1]+10}}"
            f"  {fmt_float(faith):<{col_w[2]+10}}"
            f"  {fmt_float(relev):<{col_w[3]+10}}"
            f"  {fmt_float(factu):<{col_w[4]+10}}"
            f"  {label:<{col_w[5]}}"
            f"  {verdict_str}"
        )
        print(row)

    print(sep)

    # Averages
    n = len(results)
    avg_score = sum(totals["score"]) / n
    avg_faith = sum(totals["faithfulness"]) / n
    avg_relev = sum(totals["relevancy"]) / n
    avg_factu = sum(totals["factuality"]) / n
    pass_rate = totals["pass"] / n * 100

    row = (
        f"  {'AVERAGE':<{col_w[0]}}"
        f"  {fmt_score(avg_score):<{col_w[1]+10}}"
        f"  {fmt_float(avg_faith):<{col_w[2]+10}}"
        f"  {fmt_float(avg_relev):<{col_w[3]+10}}"
        f"  {fmt_float(avg_factu):<{col_w[4]+10}}"
        f"  {'':8}"
        f"  {score_color(pass_rate/100)}{pass_rate:.0f}% pass{RESET}"
    )
    print(f"{BOLD}{row}{RESET}")
    print(f"\n  {DIM}Model: Gemini 2.5 Flash  ·  {n} test cases  ·  metrics: faithfulness / relevancy / factuality{RESET}\n")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{DIM}Running {len(GOLDEN)} golden test cases against {BACKEND} ...{RESET}\n")
    results = []

    for i, tc in enumerate(GOLDEN, 1):
        print(f"  [{i}/{len(GOLDEN)}] {tc['name']} ...", end=" ", flush=True)
        reply = get_agent_reply(tc["user"], tc["role"], tc["criteria"], tc.get("warmup"))
        result = validate(tc["user"], reply, tc["role"], tc["criteria"])
        result["name"] = tc["name"]
        results.append(result)
        label = result.get("label", "?")
        print(f"{label}")
        time.sleep(0.3)

    print_results(results)


if __name__ == "__main__":
    main()
