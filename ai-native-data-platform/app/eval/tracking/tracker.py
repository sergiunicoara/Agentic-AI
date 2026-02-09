from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class RunRecord:
    run_id: str
    created_at: float
    experiment: str
    dataset: str
    params: Dict[str, Any]
    metrics: Dict[str, Any]
    artifacts: Dict[str, Any]


def start_run(experiment: str, dataset: str, params: Dict[str, Any]) -> str:
    run_id = str(uuid.uuid4())
    _write_record(
        RunRecord(
            run_id=run_id,
            created_at=time.time(),
            experiment=experiment,
            dataset=dataset,
            params=params,
            metrics={},
            artifacts={},
        )
    )
    return run_id


def log_metrics(run_id: str, metrics: Dict[str, Any]) -> None:
    _update_record(run_id, {"metrics": metrics})


def log_artifacts(run_id: str, artifacts: Dict[str, Any]) -> None:
    _update_record(run_id, {"artifacts": artifacts})


def _runs_dir() -> Path:
    root = os.getenv("EVAL_RUNS_DIR", "runs")
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _record_path(run_id: str) -> Path:
    return _runs_dir() / f"{run_id}.json"


def _write_record(rec: RunRecord) -> None:
    _record_path(rec.run_id).write_text(json.dumps(rec.__dict__, indent=2), encoding="utf-8")


def _update_record(run_id: str, patch: Dict[str, Any]) -> None:
    p = _record_path(run_id)
    try:
        cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        cur = {}
    for k, v in patch.items():
        cur[k] = v
    p.write_text(json.dumps(cur, indent=2), encoding="utf-8")
