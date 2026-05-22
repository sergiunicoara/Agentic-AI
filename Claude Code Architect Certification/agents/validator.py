"""
CCA-F D4.4: Validation & Retry Loops
Exam concepts:
- retry-with-error-feedback (not blind retry)
- information absence vs format errors → different handling
- follow-up self-correction pattern
- semantic validation (not just schema validation)
- pattern-tracking fields to detect repeated failure types
"""
from __future__ import annotations
import json
import logging
from typing import Any
import anthropic
from pydantic import ValidationError
from schemas.rca_output import RCAOutput

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def validate_and_retry(
    client: anthropic.Anthropic,
    generate_fn: callable,
    model: str,
    messages: list[dict],
    system: str,
    tools: list[dict],
    schema_cls: type = RCAOutput,
) -> tuple[Any, list[str]]:
    """
    D4.4: Retry loop with error feedback.

    Key exam distinction:
    - Format error → retry with schema reminder + what was wrong
    - Information absence error → do NOT retry (agent doesn't have the info)
    - Semantic error → retry with specific correction instruction

    Returns (validated_result, list_of_retry_reasons)
    """
    retry_reasons = []
    failure_pattern_counts: dict[str, int] = {}  # D4.4: pattern tracking

    for attempt in range(MAX_RETRIES):
        try:
            result = generate_fn()
            # Schema validation
            if isinstance(result, dict):
                validated = schema_cls(**result)
            else:
                validated = result

            # Semantic validation (beyond schema)
            semantic_errors = _semantic_validate(validated)
            if semantic_errors:
                raise ValueError(f"Semantic validation failed: {'; '.join(semantic_errors)}")

            logger.info(f"Validated on attempt {attempt + 1}")
            return validated, retry_reasons

        except (ValidationError, ValueError, KeyError) as e:
            error_type = _classify_error(str(e))
            failure_pattern_counts[error_type] = failure_pattern_counts.get(error_type, 0) + 1
            reason = f"Attempt {attempt + 1}: {error_type} — {str(e)[:200]}"
            retry_reasons.append(reason)
            logger.warning(reason)

            # D4.4: Information absence — do NOT retry, escalate
            if error_type == "information_absence":
                logger.info("Information absence detected — not retrying, escalating")
                break

            # D4.4: Add error feedback to messages for next attempt
            messages.append({
                "role": "user",
                "content": _build_retry_feedback(error_type, str(e), attempt + 1),
            })

    # All retries exhausted
    raise RuntimeError(
        f"Validation failed after {MAX_RETRIES} attempts. "
        f"Failure patterns: {failure_pattern_counts}. "
        f"Last errors: {retry_reasons[-1] if retry_reasons else 'none'}"
    )


def _semantic_validate(rca: RCAOutput) -> list[str]:
    """
    D4.4: Semantic validation — things schema can't catch.
    Returns list of errors, empty if valid.
    """
    errors = []

    # Confidence must be numeric (not 0.0 placeholder)
    if rca.confidence == 0.0 and rca.root_cause:
        errors.append("Confidence is 0.0 but root_cause is present — likely not calibrated")

    # Severity P1 should have evidence
    if rca.severity == "P1" and not rca.evidence:
        errors.append("P1 severity requires at least one evidence item")

    # next_steps must be actionable (not generic)
    generic_steps = ["investigate", "look into", "check", "review the logs"]
    for step in (rca.next_steps or []):
        if step.lower() in generic_steps:
            errors.append(f"next_step '{step}' is too generic — be specific")

    # Escalation consistency
    if rca.escalate and not rca.escalation_reason:
        errors.append("escalate=true requires escalation_reason")

    return errors


def _classify_error(error_msg: str) -> str:
    """D4.4: Classify error type to determine retry strategy."""
    msg = error_msg.lower()
    if "missing" in msg and "field" in msg:
        return "schema_missing_field"
    if "none" in msg or "null" in msg or "not found" in msg:
        return "information_absence"   # don't retry!
    if "invalid" in msg or "enum" in msg or "type" in msg:
        return "schema_type_error"
    if "semantic" in msg or "calibrated" in msg or "generic" in msg:
        return "semantic_error"
    return "unknown_error"


def _build_retry_feedback(error_type: str, error_msg: str, attempt: int) -> str:
    """
    D4.4: retry-with-error-feedback — tell the model WHAT was wrong.
    Blind retry (same prompt again) doesn't work.
    """
    base = f"Attempt {attempt} failed. "
    if error_type == "schema_missing_field":
        return base + f"Missing required field. Error: {error_msg}. Please include all required fields."
    if error_type == "schema_type_error":
        return base + f"Type error in output. Error: {error_msg}. Check the JSON schema."
    if error_type == "semantic_error":
        return base + f"Output passed schema but failed semantic check. Fix: {error_msg}"
    return base + f"Error: {error_msg}. Please try again with corrected output."
