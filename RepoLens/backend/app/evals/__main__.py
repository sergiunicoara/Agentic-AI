import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_factory
from app.evals.runner import run_eval, write_results
from app.ingest.embedder import FakeEmbedder, OpenAIEmbedder
from app.retrieval.llm import AnthropicClient, FakeLLMClient
from app.tables import repos


async def _resolve_repo_id(session: AsyncSession, args: argparse.Namespace) -> uuid.UUID:
    if args.repo_id:
        return uuid.UUID(args.repo_id)
    result = await session.execute(select(repos.c.id).where(repos.c.source_url == args.source_url))
    row = result.first()
    if row is None:
        raise SystemExit(f"No ingested repo found with source_url={args.source_url!r}")
    return row[0]


async def main_async(args: argparse.Namespace) -> int:
    embedder = FakeEmbedder() if args.fake else OpenAIEmbedder()
    llm_client = FakeLLMClient() if args.fake else AnthropicClient()

    async with session_factory()() as session:
        repo_id = await _resolve_repo_id(session, args)
        summary = await run_eval(
            session,
            embedder,
            llm_client,
            repo_id,
            Path(args.golden),
            use_hybrid=args.hybrid,
        )

    results_path = write_results(summary, Path(args.results_dir))

    print(f"\nResults written to {results_path}\n")
    print(f"{'Metric':<24}{'Value':<12}{'Gate'}")
    print(f"{'retrieval_hit@5':<24}{summary.retrieval_hit_at_5:<12.2f}>= 0.80")
    print(f"{'answer_correctness':<24}{summary.answer_correctness:<12.2f}>= 0.80")
    print(f"{'false_refusal_rate':<24}{summary.false_refusal_rate:<12.2f}== 0.00")
    print(f"{'citation_precision':<24}{summary.citation_precision:<12.2f}>= 0.85")
    print(f"{'citation_validity':<24}{summary.citation_validity:<12.2f}== 1.00")
    print(f"{'citation_coverage':<24}{summary.citation_coverage:<12.2f}>= 0.80")
    print(f"{'groundedness':<24}{summary.groundedness:<12.2f}>= 0.70")
    print(f"{'refusal_accuracy':<24}{summary.refusal_accuracy:<12.2f}== 1.00")
    print(f"{'p95_latency_seconds':<24}{summary.p95_latency_seconds:<12.2f}(report only)")
    print()

    if not summary.passed_gates:
        print("GATE FAILURES:")
        for failure in summary.gate_failures:
            print(f"  - {failure}")
        return 1

    print("All gates passed.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the golden-set eval suite.")
    parser.add_argument("golden", help="Path to a golden-set YAML file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--repo-id", help="UUID of the ingested repo to evaluate")
    group.add_argument(
        "--source-url",
        help="Look up repo_id by the source_url it was ingested with (alternative to --repo-id)",
    )
    parser.add_argument("--hybrid", action="store_true", help="Use BM25+RRF hybrid retrieval")
    parser.add_argument("--fake", action="store_true", help="Use fake embedder/LLM (testing only)")
    parser.add_argument("--results-dir", default="evals/results")
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
