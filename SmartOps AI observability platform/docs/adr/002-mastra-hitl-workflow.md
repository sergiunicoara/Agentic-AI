# ADR-002: Mastra AI for Human-in-the-Loop Workflow

**Status**: Accepted  
**Date**: 2026-07

## Context

The alert-to-ticket flow requires: anomaly detection → root-cause analysis → **human approval** → ServiceNow ticket creation. The approval step means the workflow must pause, persist its state across an HTTP request boundary, and resume when the operator makes a decision.

This is the human-in-the-loop (HITL) primitive: a durable, resumable execution.

## Decision

Use Mastra AI's `createWorkflow` with `.suspend()` / `.resume()` for the HITL gate.

## Rationale

- **Native suspend/resume** — Mastra's workflow engine persists step state in LibSQL when `.suspend()` is called. The workflow survives process restarts. No custom job queue needed.
- **TypeScript-native** — agents, tools, and workflows are all typed. The `inputData` and `resumeData` shapes are validated at compile time via Zod.
- **Agent composition** — the four agents (anomaly detector, RCA analyzer, forecaster, ServiceNow) are independent Mastra `Agent` instances reused both inside and outside the workflow. No coupling to the orchestration layer.
- **Anthropic integration** — `@ai-sdk/anthropic` integrates directly; model swaps (Haiku ↔ Sonnet) are one-line changes per agent.

## The HITL Mechanics

```
POST /ai/workflows/alert-to-ticket
  → workflow.createRun().start()
  → runs detect-anomaly, analyze-root-cause steps
  → hits await-approval step → .suspend({ rca })
  → API writes incident row (status: pending_approval)
  → returns { runId, status: "suspended", rca }

[operator sees modal, clicks Approve/Reject]

POST /ai/workflows/:runId/resume { approved: true }
  → workflow.createRun({ runId }).resume({ step: "await-approval", resumeData: { approved } })
  → runs create-ticket step
  → API updates incident row (status: ticketed | rejected)
```

## Trade-offs

- **PostgreSQL for state** — workflow checkpoints use the shared application PostgreSQL database, so suspend/resume survives restarts and works across API replicas.
- **Same process** — `ai-agents` runs inside the Fastify process. If the Mastra workflow is CPU-intensive it could block the event loop. A separate Mastra server process is the production upgrade path.
- **Mastra version coupling** — Mastra's API surface changed significantly between 0.x and 1.x. Pinned to `^1.50.1`.

## Alternatives Considered

- **Custom Redis queue + polling** — would work but adds infrastructure and bespoke code for state persistence.
- **Temporal** — production-grade durable execution, but significant operational overhead (requires a Temporal server cluster).
- **LangGraph** — Python-first; using it from TypeScript adds a language boundary.
