# Automated rollback mechanisms (reference design)

This repository is a scaffold, but it demonstrates how rollback mechanisms are typically wired for AI-native systems.

## 1) Prevent regressions with CI evaluation gates

The workflow in `.github/workflows/eval-gates.yml` runs `python -m app.eval.run` and fails if configured gates are violated. This prevents known-bad retrieval/config/model changes from reaching main.

## 2) Canary routing with experiment-aware retrieval

Online retrieval is parameterized by experiment configs (`app/eval/experiments/*.yaml`). Requests can select an experiment via:

- Header: `X-Experiment: <experiment-name>`
- Percentage rollout: `AB_ROLLOUT_PERCENT` with stable hashing by workspace_id

A typical rollback is simply: set `AB_ROLLOUT_PERCENT=0` (or route all traffic back to `baseline`). This is configuration-only and does not require code rollback.

## 3) Deployment-level rollback (Kubernetes)

For production, pair this repo with a progressive delivery controller (e.g., Argo Rollouts). A reference rollouts spec could:

- Shift 10% traffic to the new revision
- Run an analysis job that executes the offline eval harness against a pinned dataset
- Abort and rollback if the analysis fails or if SLO alerts fire

## 4) SLO-triggered rollback

The API exports rolling SLO metrics (see `app/core/reliability/slo_window.py`). In production, an alerting rule (see `ops/prometheus/alerts.yml`) can:

- Page on p95 latency spikes and error rate
- Auto-create tickets on elevated unknown-response rate (often a retrieval regression)

An automated action system (outside the scope of this scaffold) can connect alerts to:

- Experiment router changes (fast)
- Deployment rollback (slower but more complete)

The key concept is that rollback is *not only* “revert the code”, but also “revert the retrieval configuration” and “revert the model/embedding version”.
