from __future__ import annotations

"""RAGAS evaluation for grounded generation on mixed-content corpora.

Metrics:
  faithfulness       — fraction of answer claims entailed by retrieved context
  answer_relevancy   — how relevant the answer is to the original question
  context_precision  — proportion of retrieved context that is actually useful
  context_recall     — how much of the ground-truth answer is covered by context
                       (requires ground_truth field)

Usage:
    from app.eval.ragas_eval import RagasTestCase, run_ragas_eval

    cases = [
        RagasTestCase(
            question="What is the refund policy?",
            answer="Refunds are processed within 14 days.",
            contexts=["Our refund policy allows returns within 14 business days."],
            ground_truth="Refunds take up to 14 days.",
        )
    ]
    results = run_ragas_eval(cases)
    for r in results:
        print(r.faithfulness, r.answer_relevancy)
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RagasTestCase:
    question: str
    answer: str
    contexts: list[str]         # retrieved chunk texts — works for both text and image captions
    ground_truth: str | None = None   # required for context_recall


@dataclass
class RagasResult:
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    scores: dict[str, Any] = field(default_factory=dict)


def run_ragas_eval(test_cases: list[RagasTestCase]) -> list[RagasResult]:
    """Evaluate a list of RAG outputs with RAGAS.

    Requires: pip install ragas datasets
    Set OPENAI_API_KEY — RAGAS uses an LLM judge internally for faithfulness
    and answer_relevancy.
    """
    try:
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
        from datasets import Dataset
    except ImportError as e:
        raise ImportError(
            "Install evaluation dependencies: pip install ragas datasets"
        ) from e

    data: dict[str, list] = {
        "question": [tc.question for tc in test_cases],
        "answer": [tc.answer for tc in test_cases],
        "contexts": [tc.contexts for tc in test_cases],
    }

    metrics = [faithfulness, answer_relevancy, context_precision]

    has_ground_truth = any(tc.ground_truth for tc in test_cases)
    if has_ground_truth:
        data["ground_truth"] = [tc.ground_truth or "" for tc in test_cases]
        metrics.append(context_recall)

    dataset = Dataset.from_dict(data)
    result = evaluate(dataset, metrics=metrics)
    df = result.to_pandas()

    return [
        RagasResult(
            faithfulness=_safe_float(row.get("faithfulness")),
            answer_relevancy=_safe_float(row.get("answer_relevancy")),
            context_precision=_safe_float(row.get("context_precision")),
            context_recall=_safe_float(row.get("context_recall")),
            scores=row.to_dict(),
        )
        for _, row in df.iterrows()
    ]


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None
