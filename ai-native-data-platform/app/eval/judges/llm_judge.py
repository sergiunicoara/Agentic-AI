from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.providers.llm import generate


@dataclass
class JudgeResult:
    score: float
    rationale: str


def judge_answer(query: str, predicted: str, reference: Optional[str], context: str) -> JudgeResult:
    """LLM-as-a-judge scoring (optional).

    The default LLM provider in CI is mocked (deterministic), so this will not
    introduce network calls unless LLM_PROVIDER=openai and credentials are set.

    Output schema is intentionally minimal for reliability.
    """

    prompt = f"""
You are an evaluator for a retrieval-augmented QA system.

Score the predicted answer versus the reference and the provided context.

Return ONLY valid JSON:
{{"score": <number between 0 and 1>, "rationale": "<short>"}}

Query:
{query}

Reference answer (may be empty):
{reference or ""}

Predicted answer:
{predicted}

Context:
{context}
""".strip()

    try:
        raw = generate(prompt)
        obj = json.loads(raw)
        score = float(obj.get("score", 0.0))
        rationale = str(obj.get("rationale", ""))[:400]
        score = max(0.0, min(1.0, score))
        return JudgeResult(score=score, rationale=rationale)
    except Exception as e:
        return JudgeResult(score=0.0, rationale=f"judge_error: {e}")
