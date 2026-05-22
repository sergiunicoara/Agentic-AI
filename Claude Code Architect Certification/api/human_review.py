"""
CCA-F D5.5: Human Review Workflows
Exam concept: stratified sampling, field-level calibration, threshold routing.
Aggregate accuracy can mask poor P1 performance — human review must be targeted.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from datetime import datetime
from schemas.rca_output import RCAOutput

logger = logging.getLogger(__name__)
REVIEW_QUEUE_PATH = Path(".claude/review_queue.jsonl")


class HumanReviewQueue:
    """
    D5.5: Routes escalated RCAs to human reviewers with stratified priority.

    Key exam concept: don't just check overall accuracy.
    P1 incidents with wrong severity classification need immediate review.
    Low-frequency edge cases (specific services, error types) may be
    systematically wrong even with 90%+ overall accuracy.
    """

    def enqueue(self, rca: RCAOutput):
        """Add an RCA to the human review queue with priority routing."""
        priority = self._compute_priority(rca)

        entry = {
            "ts": datetime.utcnow().isoformat(),
            "ticket_id": rca.ticket_id,
            "priority": priority,
            "severity": rca.severity,
            "confidence": rca.confidence,
            "escalation_reason": rca.escalation_reason,
            "rca": rca.to_api_response(),
        }

        REVIEW_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REVIEW_QUEUE_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")

        logger.warning(
            f"Enqueued {rca.ticket_id} for human review "
            f"[priority={priority}, confidence={rca.confidence:.2f}]"
        )

    def _compute_priority(self, rca: RCAOutput) -> str:
        """
        D5.5: Priority routing based on severity + confidence combination.
        This is field-level calibration — not just "needs review" but "needs review NOW".
        """
        if rca.severity == "P1":
            return "critical"    # P1 always gets immediate human attention
        if rca.confidence < 0.40:
            return "high"        # Very low confidence = high uncertainty
        if rca.severity == "P2":
            return "medium"
        return "low"
