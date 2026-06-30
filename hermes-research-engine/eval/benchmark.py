"""
Evaluation benchmark: 10 research questions → task completion rate.
Run: python -m eval.benchmark
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.agents.orchestrator import OrchestratorAgent
from app.observability import RequestMetrics

QUESTIONS = [
    ("Q1", "What are the key differences between transformer and state space models for sequence modeling?"),
    ("Q2", "How does retrieval-augmented generation (RAG) improve LLM factual accuracy?"),
    ("Q3", "What is the ReAct prompting technique and how does it improve agent reasoning?"),
    ("Q4", "Compare vector databases: Pinecone vs Weaviate vs Qdrant for production RAG systems."),
    ("Q5", "What are the main failure modes of LLM agents in production?"),
    ("Q6", "How does the Model Context Protocol (MCP) enable multi-step agent tool use?"),
    ("Q7", "What is prompt caching and how does it reduce LLM inference costs?"),
    ("Q8", "Explain the difference between episodic, semantic, and procedural memory in AI agents."),
    ("Q9", "What observability tools are recommended for monitoring LLM applications in production?"),
    ("Q10", "How does Tree-of-Thoughts reasoning differ from Chain-of-Thought prompting?"),
]

SCORING = {
    "has_executive_summary": lambda r: "## Executive Summary" in r or "Executive Summary" in r,
    "has_key_findings": lambda r: "## Key Findings" in r or "Key Findings" in r,
    "has_citations": lambda r: "[Source:" in r or "http" in r or "References" in r,
    "min_length": lambda r: len(r) > 300,
    "has_conclusion": lambda r: "Conclusion" in r or "conclusion" in r,
}


def score_result(result: str) -> dict:
    scores = {k: int(fn(result)) for k, fn in SCORING.items()}
    scores["total"] = sum(scores.values())
    scores["max"] = len(SCORING)
    scores["pct"] = round(scores["total"] / scores["max"] * 100)
    return scores


def run_benchmark():
    print("=" * 70)
    print("Hermes Research Engine — Benchmark")
    print("=" * 70)

    rows = []
    total_tokens = 0
    total_time = 0.0

    for q_id, question in QUESTIONS:
        trace_id = str(uuid.uuid4())
        metrics = RequestMetrics(trace_id=trace_id)

        print(f"\n[{q_id}] {question[:60]}...")
        t0 = time.perf_counter()
        try:
            orch = OrchestratorAgent(trace_id=trace_id, metrics=metrics)
            result = orch.run(question)
            elapsed = time.perf_counter() - t0
            scores = score_result(result)
            tok = metrics.total_tokens_in + metrics.total_tokens_out
            total_tokens += tok
            total_time += elapsed
            rows.append({
                "id": q_id,
                "pass": scores["pct"],
                "tokens": tok,
                "time_s": round(elapsed, 1),
                "checks": scores,
            })
            print(f"  ✓ Score: {scores['pct']}% | Tokens: {tok} | Time: {elapsed:.1f}s")
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            rows.append({"id": q_id, "pass": 0, "tokens": 0, "time_s": round(elapsed, 1), "error": str(exc)})
            print(f"  ✗ ERROR: {exc}")

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"{'ID':<6} {'Score':>6} {'Tokens':>8} {'Time':>7}")
    print("-" * 35)
    for r in rows:
        status = "✓" if r["pass"] >= 60 else "✗"
        print(f"{r['id']:<6} {status} {r['pass']:>4}%  {r.get('tokens',0):>8}  {r['time_s']:>5.1f}s")

    passed = sum(1 for r in rows if r["pass"] >= 60)
    print("-" * 35)
    print(f"Task completion rate: {passed}/{len(QUESTIONS)} ({passed/len(QUESTIONS)*100:.0f}%)")
    print(f"Total tokens used: {total_tokens:,}")
    print(f"Total wall time: {total_time:.1f}s")

    # Save results
    with open("data/benchmark_results.json", "w") as f:
        json.dump({"rows": rows, "passed": passed, "total": len(QUESTIONS)}, f, indent=2)
    print("\nResults saved to data/benchmark_results.json")


if __name__ == "__main__":
    run_benchmark()
