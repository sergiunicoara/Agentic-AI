---
# CCA-F D3.2: Project-scoped custom command
# available to: all team members (project-level, not user-level)
# context: fork   ← D3.2: isolates this command's context from main session
description: "Run full RCA investigation on a support ticket"
tools:
  - Read
  - mcp__filesystem__read_file
  - mcp__postgres__query
  - mcp__github__read_file
---

# /analyze-ticket

Run a full multi-agent RCA investigation on the given ticket.

## Usage
```
/analyze-ticket <ticket_id_or_file_path>
```

## What this does
1. Loads ticket content (ID from Postgres, or file path from filesystem)
2. Invokes coordinator agent with decomposition strategy
3. Dispatches retrieval + log + code subagents in parallel
4. Synthesizes findings into structured RCA JSON
5. Evaluates confidence — escalates to human review if confidence < 0.65

## Output format
```json
{
  "ticket_id": "...",
  "root_cause": "...",
  "severity": "P1|P2|P3|P4",
  "confidence": 0.87,
  "evidence": [{"fact": "...", "source": "...", "ts": "..."}],
  "next_steps": ["..."],
  "escalate": false,
  "escalation_reason": null
}
```

## Examples (D4.2 few-shot guidance built into command)
Good input: `INC-2047` or `data/tickets/inc_2047.txt`
Bad input: vague descriptions — always pass ticket ID or file path

## Steps
Run: `python -m agents.coordinator analyze $ARGUMENTS`
