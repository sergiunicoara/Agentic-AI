---
# CCA-F D3.3: Path-specific rules via YAML frontmatter glob patterns
paths:
  - "agents/**"
  - "agents/subagents/**"
---

# Agent Rules (applies to agents/** only)

## Mandatory patterns for every agent file

### Agentic loop (D1.1): always check stop_reason
```python
while True:
    response = client.messages.create(...)
    if response.stop_reason == "tool_use":
        # execute and append, then continue
    elif response.stop_reason == "end_turn":
        break
    elif response.stop_reason == "max_tokens":
        # compact context, continue
```

### Subagent context passing (D1.3): always explicit, never assumed
Every subagent call MUST include a `context` dict with:
- task_id: str
- parent_findings: list[str]
- relevant_facts: dict
- provenance: list[SourceRef]

### Error propagation (D5.3): structured, never silent
```python
return AgentError(
    error_type="timeout|validation|permission|business_rule",
    source="agent_name",
    recoverable=True,
    context={"attempted": ..., "fallback": ...}
)
```

### Session management (D1.7)
- Named sessions: use session_id for resumption
- Fork for divergent exploration: `fork_session(base_id, label)`
- Stale check: sessions > 30min without activity need re-grounding

## Anti-patterns (exam traps — D1.x)
- ❌ Passing full conversation history to subagents (context bloat)
- ❌ Using `while True` without max_iterations guard
- ❌ Encoding policy in prompts instead of hook interceptors
- ❌ Assuming subagents inherit coordinator memory
