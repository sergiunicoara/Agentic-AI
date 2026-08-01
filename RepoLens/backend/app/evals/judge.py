import re

from app.retrieval.llm import LLMClient

_SCORE_RE = re.compile(r"(\d+(?:\.\d+)?)")


async def score_groundedness(
    llm_client: LLMClient, question: str, context: str, answer: str
) -> float:
    """LLM-as-judge: fraction of claims in `answer` directly supported by `context`."""
    prompt = (
        "You are grading whether an AI assistant's answer is fully grounded in the "
        "provided context — i.e. every factual claim is directly supported by the "
        "context, with no fabrication or speculation beyond it.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer: {answer}\n\n"
        "Respond with ONLY a single number between 0.0 and 1.0 — the fraction of "
        "claims in the answer that are directly supported by the context. No other text."
    )
    response = await llm_client.complete(prompt)
    match = _SCORE_RE.search(response)
    if not match:
        return 0.0
    return max(0.0, min(1.0, float(match.group(1))))


async def judge_refusal(llm_client: LLMClient, answer: str) -> bool:
    """True if `answer` refuses or states it cannot determine the answer from context."""
    prompt = (
        "Does the following answer refuse to answer, or explicitly state it cannot "
        "determine the answer from the given context? Respond with ONLY 'yes' or 'no'.\n\n"
        f"Answer: {answer}"
    )
    response = await llm_client.complete(prompt)
    return response.strip().lower().startswith("y")
