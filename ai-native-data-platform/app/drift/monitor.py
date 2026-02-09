from __future__ import annotations

import json
import time

from sqlalchemy import text

from app.data.db import session_scope
from app.core.observability import persist_trace


def compute_drift_signal(workspace_id: str, window_minutes: int = 1440) -> dict:
    """Compute a lightweight drift signal from recent traces.

    This is a deliberately simple, infra-light loop:
    - aggregates unknown rate
    - aggregates average top retrieval score
    - flags a potential regression if unknown rate spikes or top score drops

    In production, you'd compute richer feature distributions and compare them to a baseline.
    """

    since = int(time.time() - window_minutes * 60)
    sql = text(
        """
        SELECT body, extract(epoch from created_at) AS ts
        FROM trace_log
        WHERE trace_type='online_signals'
          AND workspace_id=:w
          AND created_at > to_timestamp(:since)
        ORDER BY created_at DESC
        LIMIT 5000
        """
    )

    unknowns = 0
    n = 0
    top_scores: list[float] = []

    with session_scope() as db:
        rows = db.execute(sql, {"w": workspace_id, "since": since}).mappings().all()

    for r in rows:
        try:
            body = r["body"]
            if isinstance(body, str):
                body = json.loads(body)
            n += 1
            if body.get("unknown"):
                unknowns += 1
            ts = body.get("retrieval", {})
            top_scores.append(float(ts.get("top_score", 0.0)))
        except Exception:
            continue

    unknown_rate = (unknowns / n) if n else 0.0
    top_score_mean = (sum(top_scores) / len(top_scores)) if top_scores else 0.0

    return {
        "window_minutes": window_minutes,
        "num_events": n,
        "unknown_rate": unknown_rate,
        "top_score_mean": top_score_mean,
        "suspect_drift": (unknown_rate > 0.40) or (top_score_mean < 0.10),
    }


def run_drift_monitor(workspace_id: str) -> dict:
    signal = compute_drift_signal(workspace_id)
    persist_trace(
        trace_type="drift",
        workspace_id=workspace_id,
        body=signal,
        latency_ms=0,
    )
    return signal
