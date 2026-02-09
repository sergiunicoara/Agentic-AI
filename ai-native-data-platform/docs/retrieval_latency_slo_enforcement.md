# Latency SLO enforcement at the retrieval layer

Retrieval is the highest-leverage place to enforce *online* latency SLOs:

- it dominates request time before generation
- it fan-outs to multiple systems (DB/shards)
- it is sensitive to tail latency

This repo adds explicit budget enforcement to the retrieval pipeline.

## Budgets and timeouts

Config (see `app/core/config.py`):

- `retrieval_budget_ms`: total budget for retrieval work
- `retriever_timeout_ms`: DB statement timeout for first-stage retrieval
- `reranker_timeout_ms`: max time you're willing to spend reranking
- `shard_hedge_after_ms`: hedging delay for tail protection

## How it's enforced

### 1) Database-level statement timeouts

Dense and lexical retrievers call:

```sql
SET LOCAL statement_timeout = <retriever_timeout_ms>
```

This prevents “slow query = slow request” cascades.

### 2) Pipeline budget checks

`LatencyBudget` (`app/retrieval/slo.py`) tracks elapsed time and remaining budget.

The pipeline will:

- stop additional shard calls if the budget is exhausted
- skip reranking if there isn't enough remaining budget

### 3) Hedging for p95/p99

If you are routing to a single shard (fanout==1) but have multiple shards, the pipeline can hedge to a second shard after a short delay (`shard_hedge_after_ms`).

This reduces sensitivity to single-shard hiccups.

## Why this matters

Without explicit enforcement, retrieval stacks tend to drift toward:

- overly aggressive fanout
- expensive rerankers
- unbounded DB queries

…until a traffic spike turns those into an outage. Budgeting makes the system degrade gracefully.

## Production next steps

To harden this further:

- propagate per-request deadlines into every downstream dependency
- enforce per-tenant latency budgets and fairness
- export budget burn-down as metrics ("budget remaining")
- implement circuit breakers when the retrieval error rate spikes
