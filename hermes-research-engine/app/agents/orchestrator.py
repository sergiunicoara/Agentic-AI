"""
OrchestratorAgent: decomposes the research question, delegates to workers,
synthesizes results. Workers run in parallel via ThreadPoolExecutor.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import AsyncGenerator, Optional

from openai import OpenAI

from app.agents.search import make_search_agent
from app.agents.rag import make_rag_agent
from app.agents.synthesis import make_synthesis_agent
from app.memory.episodic import episodic_memory
from app.memory.long_term import long_term_memory
from app.observability import logger, RequestMetrics

# Max 2 sub-questions to minimize LLM calls
_DECOMPOSE_PROMPT = """Break the following research question into exactly 2 focused sub-questions that together fully answer it.
Return ONLY valid JSON, no other text:
{{"sub_questions": ["sub-question 1", "sub-question 2"]}}"""


def _plain_llm(prompt: str) -> str:
    client = OpenAI(
        api_key=os.environ["HF_TOKEN"],
        base_url=os.getenv("HF_BASE_URL", "https://api.deepseek.com/v1"),
    )
    resp = client.chat.completions.create(
        model=os.getenv("HERMES_MODEL", "deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=128,
    )
    return resp.choices[0].message.content or ""


def _kb_has_data() -> bool:
    """Check if the knowledge base has any documents — skip RAG if empty."""
    try:
        return long_term_memory._table.count_rows() > 0
    except Exception:
        return False


class OrchestratorAgent:
    """
    Hierarchical multi-agent orchestrator:
    1. Decomposes question into 2 sub-questions (plain LLM, no tools)
    2. Runs SearchAgent + RAGAgent (if KB non-empty) in parallel threads
    3. Feeds all results into SynthesisAgent for the final report
    4. Records episode in episodic memory
    """

    def __init__(self, trace_id: str, metrics: Optional[RequestMetrics] = None) -> None:
        self.trace_id = trace_id
        self.metrics = metrics

    def _decompose(self, question: str) -> list[str]:
        resp = _plain_llm(f"{_DECOMPOSE_PROMPT}\n\nResearch question: {question}")
        try:
            start = resp.index("{")
            end = resp.rindex("}") + 1
            data = json.loads(resp[start:end])
            return data.get("sub_questions", [question])
        except (ValueError, json.JSONDecodeError):
            return [question]

    def _research_sub_question(self, sq: str, idx: int) -> str:
        """Run search (+ optional RAG) for one sub-question. Runs in a thread."""
        search = make_search_agent(self.metrics)
        search_result = search.run(sq, self.trace_id)

        rag_result = ""
        if _kb_has_data():
            rag = make_rag_agent(self.metrics)
            rag_result = rag.run(sq, self.trace_id)

        parts = [f"### Sub-question {idx+1}: {sq}", f"**Web search:**\n{search_result}"]
        if rag_result:
            parts.append(f"**Knowledge base:**\n{rag_result}")
        return "\n\n".join(parts)

    def run(self, question: str) -> str:
        logger.step(self.trace_id, "orchestrator", "start", question=question)

        past = episodic_memory.find_similar(question, n=2)
        context_hint = ""
        if past:
            summaries = "\n".join(f"- {ep['summary']}" for ep in past)
            context_hint = f"\n\nRelated past research:\n{summaries}"

        sub_questions = self._decompose(question + context_hint)
        logger.step(self.trace_id, "orchestrator", "decomposed", sub_questions=sub_questions)

        # Run all sub-questions in parallel
        gathered = [""] * len(sub_questions)
        with ThreadPoolExecutor(max_workers=len(sub_questions)) as pool:
            futures = {
                pool.submit(self._research_sub_question, sq, i): i
                for i, sq in enumerate(sub_questions)
            }
            for future in as_completed(futures):
                idx = futures[future]
                gathered[idx] = future.result()
                logger.step(self.trace_id, "orchestrator", "worker_done", worker_idx=idx)

        combined = f"Research question: {question}\n\n" + "\n\n---\n\n".join(gathered)
        synthesis = make_synthesis_agent(self.metrics)
        final_report = synthesis.run(combined, self.trace_id)

        if self.metrics:
            episodic_memory.record(
                task_id=self.trace_id,
                question=question,
                summary=final_report[:300],
                tokens_used=self.metrics.total_tokens_in + self.metrics.total_tokens_out,
            )

        logger.step(self.trace_id, "orchestrator", "complete")
        return final_report

    async def stream(self, question: str) -> AsyncGenerator[str, None]:
        import asyncio
        logger.step(self.trace_id, "orchestrator", "start", question=question)
        yield json.dumps({"type": "status", "msg": "Decomposing research question..."})

        past = episodic_memory.find_similar(question, n=2)
        context_hint = ""
        if past:
            summaries = "\n".join(f"- {ep['summary']}" for ep in past)
            context_hint = f"\n\nRelated past research:\n{summaries}"
            yield json.dumps({"type": "status", "msg": f"Found {len(past)} related past session(s)"})

        sub_questions = self._decompose(question + context_hint)
        yield json.dumps({"type": "decomposed", "sub_questions": sub_questions})
        yield json.dumps({"type": "status", "msg": f"Running {len(sub_questions)} workers in parallel..."})

        # Parallel execution via thread pool
        gathered = [""] * len(sub_questions)
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=len(sub_questions)) as pool:
            futures = {
                pool.submit(self._research_sub_question, sq, i): i
                for i, sq in enumerate(sub_questions)
            }
            for future in as_completed(futures):
                idx = futures[future]
                gathered[idx] = future.result()
                yield json.dumps({"type": "worker_done", "worker_idx": idx, "sub_q": sub_questions[idx]})

        yield json.dumps({"type": "status", "msg": "Synthesizing final report..."})
        combined = f"Research question: {question}\n\n" + "\n\n---\n\n".join(gathered)
        synthesis = make_synthesis_agent(self.metrics)
        final_report = synthesis.run(combined, self.trace_id)

        if self.metrics:
            episodic_memory.record(
                task_id=self.trace_id,
                question=question,
                summary=final_report[:300],
                tokens_used=self.metrics.total_tokens_in + self.metrics.total_tokens_out,
            )

        yield json.dumps({"type": "final_report", "content": final_report})
        if self.metrics:
            yield json.dumps({"type": "metrics", "data": self.metrics.summary()})
