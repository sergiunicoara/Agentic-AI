---
# CCA-F D3.3: Path-specific rules — MCP servers
paths:
  - "mcp/**"
---

# MCP Server Rules (applies to mcp/** only)

## Tool description standard (D2.1 — exam's most-overlooked area)
Every tool MUST follow: VERB + NOUN + BOUNDARY + CONSTRAINTS
```
Good: "Search incident tickets by keyword within the last N days. Returns up to 50 results."
Bad:  "Search tickets"  ← too vague, causes misrouting
Bad:  "Finds things in the database"  ← no boundary, no constraints
```

## Structured error responses (D2.2)
ALL MCP tools must return errors using the isError pattern:
```python
return CallToolResult(
    isError=True,
    content=[TextContent(text=json.dumps({
        "error_type": "transient|validation|business|permission",
        "message": "...",
        "recoverable": True,
        "retry_after": 5,   # seconds, if transient
        "context": {}
    }))]
)
```
Error categories:
- transient   → network/timeout, recoverable=True, include retry_after
- validation  → bad input, recoverable=False, include expected_format
- business    → policy violation, recoverable=False, escalate=True
- permission  → auth failure, recoverable=False, escalate=True

## MCP configuration levels (D2.4 — exam trap)
- Project tools → .mcp.json (committed, shared with team)
- Personal/dev tools → ~/.claude/mcp.json (user level, NOT committed)
- Environment secrets → env vars, never hardcoded in .mcp.json

## Tool overload prevention (D2.3)
- Max 8 tools per server before splitting into specialized servers
- Role-scoped: give agents only the tools they need
- Use `tool_choice: {"type": "tool", "name": "..."}` to force specific tools
