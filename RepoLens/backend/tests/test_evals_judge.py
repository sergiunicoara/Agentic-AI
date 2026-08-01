from app.evals.judge import judge_refusal, score_groundedness
from app.retrieval.llm import FakeLLMClient


async def test_score_groundedness_parses_number() -> None:
    llm_client = FakeLLMClient(canned_completion="0.75")
    score = await score_groundedness(llm_client, "q", "context", "answer")
    assert score == 0.75
    assert llm_client.last_prompt is not None
    assert "context" in llm_client.last_prompt


async def test_score_groundedness_clamps_above_one() -> None:
    llm_client = FakeLLMClient(canned_completion="1.5")
    assert await score_groundedness(llm_client, "q", "c", "a") == 1.0


async def test_score_groundedness_defaults_zero_on_unparseable_response() -> None:
    llm_client = FakeLLMClient(canned_completion="no idea")
    assert await score_groundedness(llm_client, "q", "c", "a") == 0.0


async def test_judge_refusal_true_on_yes() -> None:
    llm_client = FakeLLMClient(canned_completion="yes")
    assert await judge_refusal(llm_client, "I don't know") is True


async def test_judge_refusal_false_on_no() -> None:
    llm_client = FakeLLMClient(canned_completion="no")
    assert await judge_refusal(llm_client, "The answer is 42.") is False
