from __future__ import annotations

"""Automated remediation loop.

This module demonstrates a simple closed-loop ops pattern:

  observe rolling SLOs -> detect sustained violation -> apply mitigation

Mitigations are conservative and reversible:
  - force all traffic to a safe control experiment (A/B override)

In a production platform this logic would likely live in a separate controller
service and interact with a feature flag system / deployment system.
"""

from sqlalchemy import text

from app.data.db import write_session_scope


def _write_override(experiment: str) -> None:
    with write_session_scope() as db:
        db.execute(
            text(
                """
                INSERT INTO runtime_experiment_override (scope, experiment, updated_at)
                VALUES ('global', :experiment, now())
                ON CONFLICT (scope)
                DO UPDATE SET experiment = EXCLUDED.experiment, updated_at = now()
                """
            ),
            {"experiment": experiment},
        )


def clear_override() -> None:
    with write_session_scope() as db:
        db.execute(text("DELETE FROM runtime_experiment_override WHERE scope = 'global'"))


def has_override() -> bool:
    """Whether a global override row currently exists.

    Used by the controller at leader-acquisition time to seed its local
    override-tracking state from the actual DB row, rather than assuming
    "no override" just because this process wasn't the one that applied it
    (e.g. after a leadership handoff mid-remediation).
    """
    with write_session_scope() as db:
        row = db.execute(text("SELECT 1 FROM runtime_experiment_override WHERE scope = 'global'")).first()
        return row is not None

# NOTE: the only remediation loop that actually runs is the leader-elected
# one in remediation_controller.py::start_controller(). A prior, unguarded
# duplicate of this loop (start_remediation_loop) lived here — it ran on
# every replica with no leader coordination, which is exactly the
# multi-writer race leader election exists to prevent. It had no callers
# anywhere in the app and has been removed rather than left as a footgun.
