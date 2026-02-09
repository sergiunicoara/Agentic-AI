from __future__ import annotations

import hashlib
import json
from pathlib import Path
from dataclasses import dataclass

from app.core.config import settings


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

    # Automated remediation can set an override file to force all traffic
    # to a safe control experiment.
    override_path = Path(".runtime/ab_override.json")
    if override_path.exists():
        try:
            data = json.loads(override_path.read_text(encoding="utf-8"))
            forced = data.get("force_all") or data.get("force_by_workspace", {}).get(workspace_id)
            if forced:
                return ExperimentAssignment(name=str(forced), reason="remediation_override")
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
