"""
CCA-F D5.3: Error Propagation in Multi-Agent Systems
Exam concepts:
- Structured error context: error_type, source, recoverable, context
- Access errors vs empty results (different handling!)
- Local recovery before propagation
- Coverage annotation (mark what was skipped due to error)
"""
from __future__ import annotations
import logging
from schemas.rca_output import AgentError

logger = logging.getLogger(__name__)


def propagate_error(
    error: AgentError,
    source: str,
    task: str,
    attempt_recovery: bool = True,
) -> AgentError:
    """
    D5.3: Propagate error up the agent chain with enriched context.
    Local recovery attempted first; only propagates if unrecoverable.
    """
    enriched = AgentError(
        error_type=error.error_type,
        source=f"{source}.{error.source}",  # chain: coordinator.retrieval_agent
        recoverable=error.recoverable,
        context={
            **error.context,
            "propagated_via": source,
            "failed_task": task,
            "coverage": f"Task '{task}' skipped — partial results only",
        }
    )

    if error.recoverable and attempt_recovery:
        logger.warning(f"Recoverable error from {error.source} in task {task}: {error.error_type}")
        # Return partial result annotation rather than hard failure
        return enriched

    logger.error(f"Unrecoverable error from {error.source}: {error.error_type}")
    return enriched


def classify_empty_vs_error(result: dict) -> str:
    """
    D5.3 exam concept: distinguish access errors from empty results.
    These require different handling:
    - Empty result: agent worked, nothing found → partial analysis OK
    - Access error: agent couldn't reach data → unknown coverage → must flag
    """
    if not result:
        return "empty_result"
    if result.get("error_type") in ("permission", "timeout", "connection"):
        return "access_error"
    if result.get("findings") == [] or result.get("results") == []:
        return "empty_result"
    return "success"


def build_coverage_annotation(skipped_agents: list[str]) -> dict:
    """
    D5.3: Annotate what coverage was missing due to errors.
    The final report must note what wasn't investigated.
    """
    if not skipped_agents:
        return {"coverage": "complete"}
    return {
        "coverage": "partial",
        "skipped_agents": skipped_agents,
        "coverage_note": f"Analysis excludes: {', '.join(skipped_agents)}. "
                         f"Results may be incomplete.",
    }
