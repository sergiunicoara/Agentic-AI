"""
eval/compare_versions.py — Side-by-side eval comparison between two Cloud Run revisions.

Runs the same 6 golden test cases against OLD and NEW simultaneously (two threads),
then prints a delta table: score, faithfulness, relevancy, factuality per test case.

Usage
-----
    python eval/compare_versions.py <old_url> <new_url>

    # Or with env vars:
    OLD_URL=https://baseline---... NEW_URL=https://... python eval/compare_versions.py
"""
from __future__ import annotations

import os
import sys
import time
import threading
from typing import Optional

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── ANSI colours ──────────────────────────────────────────────────────────────

RESET  = "\033[0m"; BOLD   = "\033[1m"; DIM    = "\033[2m"
GREEN  = "\033[92m"; YELLOW = "\033[93m"; RED    = "\033[91m"
CYAN   = "\033[96m"; BLUE   = "\033[94m"

def _c(v: float, lo: float = 0.6, hi: float = 0.8) -> str:
    if v >= hi:  return GREEN
    if v >= lo:  return YELLOW
    return RED

def _delta(new: float, old: float) -> str:
    d = new - old
    if abs(d) < 0.01:  return f"{DIM}  ={RESET}"
    return f"{GREEN}+{d:.2f}{RESET}" if d > 0 else f"{RED}{d:.2f}{RESET}"

# ── Golden dataset (same as run_eval_table.py) ────────────────────────────────

GOLDEN = [
    {
        "name": "Role extraction — voice AI",
        "user": "We're hiring a Lead AI Engineer with hands-on voice pipeline experience — STT/TTS, real-time streaming, RAG.",
        "role": "Lead AI Engineer",
        "criteria": ["voice_ai", "production_rag", "low_latency"],
    },
    {
        "name": "Criteria parsing — observability",
        "user": "Senior ML Engineer. We care about LLM observability, OTel tracing, and evaluation harnesses.",
        "role": "Senior ML Engineer",
        "criteria": ["observability"],
    },
    {
        "name": "Project deep dive — RAG",
        "user": "1",
        "role": "LLM Engineer",
        "criteria": ["production_rag", "ownership"],
        "warmup": ["LLM Engineer", "production RAG, ownership"],
    },
    {
        "name": "CV Q&A — certifications",
        "user": "Which certifications does Sergiu have?",
        "role": "AI Engineer",
        "criteria": ["communication"],
    },
    {
        "name": "ATS summary quality",
        "user": "2",
        "role": "Senior Voice AI Engineer",
        "criteria": ["voice_ai", "production_rag", "observability"],
        "warmup": ["Senior Voice AI Engineer", "voice AI, production RAG, observability"],
    },
    {
        "name": "Shortcut without role — guard",
        "user": "1",
        "role": None,
        "criteria": [],
    },
]

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _chat(base: str, session_id: str, msg: str, state=None):
    try:
        r = requests.post(
            f"{base}/chat",
            json={"session_id": session_id, "message": msg, "source": "eval", "state": state},
            timeout=25,
        )
        r.raise_for_status()
        d = r.json()
        return d.get("reply", ""), d.get("state")
    except Exception as e:
        return f"[error: {e}]", state


def _validate(base: str, user: str, reply: str, role, criteria) -> dict:
    try:
        r = requests.post(
            f"{base}/a2a/validate",
            json={
                "user_message": user, "agent_reply": reply,
                "role": role, "criteria": criteria,
                "session_id": f"cmp-{int(time.time()*1000)}",
            },
            timeout=35,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"verdict": "ERROR", "score": 0, "faithfulness": 0,
                "relevancy": 0, "factuality": 0, "label": "error", "reasoning": str(e)}


def run_suite(base: str, label: str, results: list) -> None:
    """Run all golden test cases against *base* and append to *results*."""
    print(f"  {DIM}[{label}] starting {len(GOLDEN)} cases against {base}{RESET}")
    for i, tc in enumerate(GOLDEN, 1):
        sid = f"cmp-{label}-{int(time.time()*1000)}"
        state = None
        for warmup_msg in tc.get("warmup", []):
            _, state = _chat(base, sid, warmup_msg, state)
            time.sleep(0.1)
        reply, _ = _chat(base, sid, tc["user"], state)
        v = _validate(base, tc["user"], reply, tc["role"], tc["criteria"])
        v["name"] = tc["name"]
        results.append(v)
        print(f"  {DIM}[{label}] {i}/{len(GOLDEN)} {tc['name'][:40]} → {v.get('label','?')}{RESET}")
        time.sleep(0.2)
    print(f"  {DIM}[{label}] done{RESET}")

# ── Comparison table ──────────────────────────────────────────────────────────

def print_comparison(old_results: list, new_results: list, old_label: str, new_label: str):
    old_by_name = {r["name"]: r for r in old_results}
    new_by_name = {r["name"]: r for r in new_results}

    sep = "-" * 108
    print(f"\n{BOLD}{CYAN}{sep}{RESET}")
    print(f"{BOLD}{CYAN}  Revision Comparison: {old_label}  →  {new_label}{RESET}")
    print(f"{BOLD}{CYAN}{sep}{RESET}\n")

    hdr = (
        f"  {'Test Case':<34}  "
        f"{'Score':>9}  {'Δ':>5}  "
        f"{'Faith':>9}  {'Δ':>5}  "
        f"{'Relev':>9}  {'Δ':>5}  "
        f"{'Factu':>9}  {'Δ':>5}  "
        f"{'Verdict':<10}"
    )
    print(f"{BOLD}{hdr}{RESET}")
    print(sep)

    totals = {"old_score": [], "new_score": [], "old_f": [], "new_f": [],
              "old_r": [], "new_r": [], "old_fa": [], "new_fa": [],
              "old_pass": 0, "new_pass": 0}

    for tc in GOLDEN:
        name = tc["name"]
        o = old_by_name.get(name, {})
        n = new_by_name.get(name, {})

        os_ = float(o.get("score", 0));        ns_ = float(n.get("score", 0))
        of  = float(o.get("faithfulness", 0)); nf  = float(n.get("faithfulness", 0))
        or_ = float(o.get("relevancy", 0));    nr  = float(n.get("relevancy", 0))
        ofa = float(o.get("factuality", 0));   nfa = float(n.get("factuality", 0))

        totals["old_score"].append(os_); totals["new_score"].append(ns_)
        totals["old_f"].append(of);      totals["new_f"].append(nf)
        totals["old_r"].append(or_);     totals["new_r"].append(nr)
        totals["old_fa"].append(ofa);    totals["new_fa"].append(nfa)
        if o.get("verdict") == "PASS":   totals["old_pass"] += 1
        if n.get("verdict") == "PASS":   totals["new_pass"] += 1

        verdict = n.get("verdict", "?")
        v_str = f"{GREEN}PASS ✓{RESET}" if verdict == "PASS" else f"{RED}FAIL ✗{RESET}"

        row = (
            f"  {name[:34]:<34}  "
            f"{_c(ns_/5)}{ns_:.1f}/5{RESET}{'':>2}{_delta(ns_, os_):>5}  "
            f"{_c(nf)}{nf:.2f}{RESET}{'':>2}{_delta(nf, of):>5}  "
            f"{_c(nr)}{nr:.2f}{RESET}{'':>2}{_delta(nr, or_):>5}  "
            f"{_c(nfa)}{nfa:.2f}{RESET}{'':>2}{_delta(nfa, ofa):>5}  "
            f"{v_str}"
        )
        print(row)

    print(sep)
    n_cases = len(GOLDEN)
    avgs = {k: sum(v)/len(v) if v else 0 for k, v in totals.items() if isinstance(v, list)}

    old_pass_rate = totals["old_pass"] / n_cases * 100
    new_pass_rate = totals["new_pass"] / n_cases * 100

    avg_row = (
        f"  {'AVERAGE':<34}  "
        f"{_c(avgs['new_score']/5)}{avgs['new_score']:.1f}/5{RESET}{'':>2}{_delta(avgs['new_score'], avgs['old_score']):>5}  "
        f"{_c(avgs['new_f'])}{avgs['new_f']:.2f}{RESET}{'':>2}{_delta(avgs['new_f'], avgs['old_f']):>5}  "
        f"{_c(avgs['new_r'])}{avgs['new_r']:.2f}{RESET}{'':>2}{_delta(avgs['new_r'], avgs['old_r']):>5}  "
        f"{_c(avgs['new_fa'])}{avgs['new_fa']:.2f}{RESET}{'':>2}{_delta(avgs['new_fa'], avgs['old_fa']):>5}  "
        f"{_c(new_pass_rate/100)}{new_pass_rate:.0f}% pass{RESET}"
    )
    print(f"{BOLD}{avg_row}{RESET}")

    # Summary banner
    score_delta = avgs["new_score"] - avgs["old_score"]
    banner_col = GREEN if score_delta >= 0 else RED
    print(f"\n  {BOLD}Avg score: {old_label}={avgs['old_score']:.2f}  →  "
          f"{new_label}={avgs['new_score']:.2f}  "
          f"({banner_col}{'+' if score_delta >= 0 else ''}{score_delta:.2f}{RESET}{BOLD}){RESET}")
    print(f"  {BOLD}Pass rate: {old_label}={old_pass_rate:.0f}%  →  "
          f"{new_label}={new_pass_rate:.0f}%{RESET}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    old_url = args[0] if len(args) > 0 else os.getenv("OLD_URL", "")
    new_url = args[1] if len(args) > 1 else os.getenv("NEW_URL", "")

    if not old_url or not new_url:
        print("Usage: python eval/compare_versions.py <old_url> <new_url>")
        sys.exit(1)

    old_url = old_url.rstrip("/")
    new_url = new_url.rstrip("/")

    old_label = "baseline"
    new_label = "new"

    print(f"\n{BOLD}Running parallel eval: {old_label} vs {new_label}{RESET}")
    print(f"  old → {old_url}")
    print(f"  new → {new_url}\n")

    old_results: list = []
    new_results: list = []

    # Run both suites in parallel threads
    t_old = threading.Thread(target=run_suite, args=(old_url, old_label, old_results))
    t_new = threading.Thread(target=run_suite, args=(new_url, new_label, new_results))

    t_old.start()
    t_new.start()
    t_old.join()
    t_new.join()

    if old_results and new_results:
        print_comparison(old_results, new_results, old_label, new_label)
    else:
        print(f"{RED}One or both eval runs returned no results.{RESET}")


if __name__ == "__main__":
    main()
