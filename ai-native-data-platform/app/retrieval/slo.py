from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class LatencyBudget:
    """Simple per-request latency budget.

    This is intentionally small and dependency-free: it is used to enforce
    online tail latency constraints in the retrieval path.

    Budgets are checked *proactively* to avoid spending time on stages that are
    unlikely to complete within the remaining budget.
    """

    total_ms: int
    started_at: float

    @classmethod
    def start(cls, total_ms: int) -> "LatencyBudget":
        return cls(total_ms=int(total_ms), started_at=time.time())

    def elapsed_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)

    def remaining_ms(self) -> int:
        return max(0, self.total_ms - self.elapsed_ms())

    def expired(self) -> bool:
        return self.elapsed_ms() >= self.total_ms

    def allow(self, stage_ms: int) -> bool:
        """Returns True if we can still afford a stage that needs stage_ms."""
        return self.remaining_ms() >= int(stage_ms)
