---
description: "Submit a JSONL file of tickets to the Message Batches API (50% cost savings)"
context: fork
tools:
  - Bash
  - Read
---

# /batch-process

Submit multiple tickets for analysis using the Anthropic Message Batches API.

## When to use (D4.5 exam concept)
- Processing >10 tickets simultaneously
- Latency of up to 24 hours is acceptable
- Cost reduction is a priority (50% savings vs synchronous)

## When NOT to use
- Real-time/interactive use cases
- SLA requires <1 minute response
- Single ticket investigation

## Usage
```
/batch-process data/tickets.jsonl
/batch-process data/tickets.jsonl --wait   # poll until complete
```

## Steps
Run: `python -m api.batch $ARGUMENTS`
