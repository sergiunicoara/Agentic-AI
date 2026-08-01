import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.evals.judge import judge_refusal, score_groundedness
from app.evals.metrics import (
    answer_mentions,
    retrieval_hit,
)
from app.evals.metrics import (
    citation_precision as compute_citation_precision,
)
from app.evals.metrics import (
    citation_validity as compute_citation_validity,
)
from app.evals.models import GoldenQuestion, MetricsSummary, QuestionResult
from app.ingest.embedder import Embedder
from app.retrieval.citations import extract_citations, validate_citations
from app.retrieval.context import assemble_context
from app.retrieval.llm import SYSTEM_PROMPT, LLMClient
from app.retrieval.search import search_chunks, search_chunks_hybrid

GATE_RETRIEVAL_HIT = 0.80
GATE_ANSWER_CORRECTNESS = 0.80
GATE_FALSE_REFUSAL_RATE = 0.0
GATE_CITATION_PRECISION = 0.85
GATE_CITATION_VALIDITY = 1.0
GATE_CITATION_COVERAGE = 0.80
GATE_GROUNDEDNESS = 0.70
GATE_REFUSAL_ACCURACY = 1.0


def load_golden_set(path: Path) -> list[GoldenQuestion]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [GoldenQuestion(**item) for item in data]


def _p95(latencies: list[float]) -> float:
    if not latencies:
        return 0.0
    ordered = sorted(latencies)
    index = min(max(0, int(len(ordered) * 0.95) - 1), len(ordered) - 1)
    return ordered[index]


async def run_question(
    session: AsyncSession,
    embedder: Embedder,
    llm_client: LLMClient,
    repo_id: uuid.UUID,
    question: GoldenQuestion,
    use_hybrid: bool,
) -> QuestionResult:
    started = time.monotonic()

    if use_hybrid:
        retrieved = await search_chunks_hybrid(
            session, embedder, repo_id, question.question, top_k=5
        )
    else:
        retrieved = await search_chunks(session, embedder, repo_id, question.question, top_k=5)

    context, included = assemble_context(retrieved)

    answer_parts: list[str] = []
    async for delta in llm_client.stream_reply(SYSTEM_PROMPT, [], context, question.question):
        answer_parts.append(delta)
    answer = "".join(answer_parts)

    extracted_citations = extract_citations(answer)
    citations = validate_citations(extracted_citations, included)

    hit = retrieval_hit(question.expected_files, retrieved)
    precision = compute_citation_precision(citations, question.expected_symbols, included)
    refused = await judge_refusal(llm_client, answer)
    refusal_correct = refused if question.expects_refusal else None
    false_refusal = refused if not question.expects_refusal else False
    answer_correct = (
        refused is False and answer_mentions(answer, question.answer_must_mention)
        if not question.expects_refusal
        else refused
    )
    citation_required = not question.expects_refusal and bool(
        question.expected_files or question.expected_symbols
    )
    citation_coverage = (
        None
        if question.expects_refusal
        else (bool(citations) if citation_required else True)
    )
    groundedness = (
        None
        if question.expects_refusal
        else await score_groundedness(llm_client, question.question, context, answer)
    )

    return QuestionResult(
        id=question.id,
        question=question.question,
        retrieval_hit=hit,
        answer_correct=answer_correct,
        false_refusal=false_refusal,
        citation_validity=compute_citation_validity(extracted_citations, included),
        citation_coverage=citation_coverage,
        citation_precision=precision,
        groundedness=groundedness,
        refusal_correct=refusal_correct,
        refused=refused,
        latency_seconds=time.monotonic() - started,
        answer=answer,
    )


async def run_eval(
    session: AsyncSession,
    embedder: Embedder,
    llm_client: LLMClient,
    repo_id: uuid.UUID,
    golden_path: Path,
    use_hybrid: bool = False,
) -> MetricsSummary:
    questions = load_golden_set(golden_path)
    results = [
        await run_question(session, embedder, llm_client, repo_id, q, use_hybrid) for q in questions
    ]

    hit_values = [r.retrieval_hit for r in results if r.retrieval_hit is not None]
    hit_rate = sum(hit_values) / len(hit_values) if hit_values else 0.0

    answer_correctness = sum(r.answer_correct for r in results) / len(results) if results else 0.0
    answerable = [r for r in results if r.refusal_correct is None]
    false_refusal_rate = (
        sum(r.false_refusal for r in answerable) / len(answerable) if answerable else 0.0
    )

    citation_validity_values = [r.citation_validity for r in results if r.refusal_correct is None]
    citation_validity_rate = (
        sum(citation_validity_values) / len(citation_validity_values)
        if citation_validity_values
        else 0.0
    )
    coverage_values = [r.citation_coverage for r in results if r.citation_coverage is not None]
    citation_coverage_rate = sum(coverage_values) / len(coverage_values) if coverage_values else 0.0

    precision_values = [r.citation_precision for r in results if r.citation_precision is not None]
    precision_rate = sum(precision_values) / len(precision_values) if precision_values else 0.0

    groundedness_values = [r.groundedness for r in results if r.groundedness is not None]
    groundedness_rate = (
        sum(groundedness_values) / len(groundedness_values)
        if groundedness_values
        else 0.0
    )

    refusal_results = [r.refusal_correct for r in results if r.refusal_correct is not None]
    refusal_accuracy = sum(refusal_results) / len(refusal_results) if refusal_results else 0.0

    p95_latency = _p95([r.latency_seconds for r in results])

    gate_failures = []
    if hit_rate < GATE_RETRIEVAL_HIT:
        gate_failures.append(f"retrieval_hit@5 {hit_rate:.2f} < {GATE_RETRIEVAL_HIT}")
    if answer_correctness < GATE_ANSWER_CORRECTNESS:
        gate_failures.append(
            f"answer_correctness {answer_correctness:.2f} < {GATE_ANSWER_CORRECTNESS}"
        )
    if false_refusal_rate > GATE_FALSE_REFUSAL_RATE:
        gate_failures.append(
            f"false_refusal_rate {false_refusal_rate:.2f} > {GATE_FALSE_REFUSAL_RATE}"
        )
    if precision_rate < GATE_CITATION_PRECISION:
        gate_failures.append(f"citation_precision {precision_rate:.2f} < {GATE_CITATION_PRECISION}")
    if citation_validity_rate < GATE_CITATION_VALIDITY:
        gate_failures.append(
            f"citation_validity {citation_validity_rate:.2f} < {GATE_CITATION_VALIDITY}"
        )
    if citation_coverage_rate < GATE_CITATION_COVERAGE:
        gate_failures.append(
            f"citation_coverage {citation_coverage_rate:.2f} < {GATE_CITATION_COVERAGE}"
        )
    if groundedness_rate < GATE_GROUNDEDNESS:
        gate_failures.append(f"groundedness {groundedness_rate:.2f} < {GATE_GROUNDEDNESS}")
    if refusal_accuracy < GATE_REFUSAL_ACCURACY:
        gate_failures.append(f"refusal_accuracy {refusal_accuracy:.2f} < {GATE_REFUSAL_ACCURACY}")

    return MetricsSummary(
        retrieval_hit_at_5=hit_rate,
        answer_correctness=answer_correctness,
        false_refusal_rate=false_refusal_rate,
        citation_validity=citation_validity_rate,
        citation_coverage=citation_coverage_rate,
        citation_precision=precision_rate,
        groundedness=groundedness_rate,
        refusal_accuracy=refusal_accuracy,
        p95_latency_seconds=p95_latency,
        total_questions=len(results),
        passed_gates=not gate_failures,
        gate_failures=gate_failures,
        results=results,
    )


def write_results(summary: MetricsSummary, results_dir: Path) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    timestamped_path = results_dir / f"{timestamp}.json"
    latest_path = results_dir / "latest.json"

    payload = summary.model_dump_json(indent=2)
    timestamped_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return timestamped_path
