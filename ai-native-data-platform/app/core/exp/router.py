from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import text

from app.core.config import settings
from app.data.db import read_session_scope


@dataclass(frozen=True)
class ExperimentAssignment:
    name: str
    reason: str


def _stable_percent(key: str) -> int:
    h = hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()
    return int(h[:8], 16) % 100


def choose_experiment(workspace_id: str, requested: str | None = None) -> ExperimentAssignment:
    """Choose an experiment for this request.

    Precedence:
    1) Explicit request via header (X-Experiment)
    2) Stable rollout percent to treatment
    3) Default experiment
    """

    # Overrides live in Postgres so every API replica observes remediation.
    try:
        with read_session_scope() as db:
            row = db.execute(
                text("SELECT experiment FROM runtime_experiment_override WHERE scope = 'global'"),
            ).mappings().first()
        if row and row.get("experiment"):
            return ExperimentAssignment(name=str(row["experiment"]), reason="remediation_override")
    except Exception:
        pass

    if requested:
        return ExperimentAssignment(name=requested, reason="header")

    p = int(settings.ab_rollout_percent or 0)
    if p > 0:
        bucket = _stable_percent(workspace_id)
        if bucket < p:
            return ExperimentAssignment(name=settings.ab_treatment_experiment, reason=f"rollout_{p}%")

    return ExperimentAssignment(name=settings.ab_default_experiment, reason="default")
