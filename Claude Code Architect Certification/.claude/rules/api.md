---
# CCA-F D3.3: Path-specific rules — API layer
paths:
  - "api/**"
---

# API Rules (applies to api/** only)

## Batch processing (D4.5)
Use Message Batches API when:
- Processing >10 tickets simultaneously
- Latency requirement is >1 minute acceptable
- Cost is a constraint (50% savings vs synchronous)

```python
# Correct batch pattern
batch = client.messages.batches.create(requests=[...])
# Poll or webhook — never block synchronously on batch
```

## CI/CD non-interactive mode (D3.6)
All API endpoints called from CI must use:
- `--output-format json` for machine-readable output
- `-p` flag / headless mode for non-interactive pipelines
- Handle partial failures: log per-item errors, don't fail entire batch

## Endpoint contracts
All endpoints return either:
- `{"status": "ok", "data": {...}}`
- `{"status": "error", "error": AgentError}`
Never return raw Python exceptions to clients.
