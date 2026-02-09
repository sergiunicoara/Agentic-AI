from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.core.observability import RELIABILITY_VIOLATIONS


@dataclass(frozen=True)
class ReliabilityContract:
    """Runtime guardrails for RAG quality and latency.

    In a real platform these would be backed by SLOs and alerting.
    Here we enforce them in the API path and in offline evaluation.
    """

    # Per-request hard ceiling. This is enforceable online.
    max_request_latency_ms: int
    max_empty_retrieval_rate: float
    min_groundedness_mean: float


def default_contract() -> ReliabilityContract:
    return ReliabilityContract(
        max_request_latency_ms=settings.max_request_latency_ms,
        max_empty_retrieval_rate=settings.max_empty_retrieval_rate,
        min_groundedness_mean=settings.min_groundedness_mean,
    )


class ReliabilityViolation(RuntimeError):
    pass


def enforce_latency(latency_ms: int, contract: ReliabilityContract) -> None:
    if latency_ms > contract.max_request_latency_ms:
        RELIABILITY_VIOLATIONS.labels(type="latency").inc()
        raise ReliabilityViolation(
            f"Request latency ceiling violated: {latency_ms}ms > {contract.max_request_latency_ms}ms"
        )


def enforce_non_empty(retrieved_count: int, contract: ReliabilityContract) -> None:
    if retrieved_count <= 0:
        RELIABILITY_VIOLATIONS.labels(type="empty_retrieval").inc()
        raise ReliabilityViolation("Empty retrieval")


def enforce_groundedness(groundedness: float, contract: ReliabilityContract) -> None:
    """Cheap online guard for attribution discipline.

    Offline evaluation computes groundedness as a binary signal (1.0 if all
    citations are exact substrings and minimum evidence threshold is met).
    For online traffic, we enforce the same score against the configured
    threshold as a pragmatic approximation.
    """

    if groundedness < float(contract.min_groundedness_mean):
        RELIABILITY_VIOLATIONS.labels(type="groundedness").inc()
        raise ReliabilityViolation(
            f"Groundedness floor violated: {groundedness:.3f} < {float(contract.min_groundedness_mean):.3f}"
        )
