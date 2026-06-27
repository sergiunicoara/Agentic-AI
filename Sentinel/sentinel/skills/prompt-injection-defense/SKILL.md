---
name: prompt-injection-defense
description: Detect direct and indirect prompt-injection surfaces in agent tools.
triggers: [web_fetch, file_read, user_content, rag_retrieval, eval, exec]
pillar: 3
---

## What to look for
- Tool output concatenated directly into a system or user prompt without delimiting
- `eval()` or `exec()` called on external/user-supplied content
- `subprocess` calls with `shell=True` and user-controlled input
- F-strings or `.format()` used to build prompts from untrusted sources
- No input sanitization before tool results enter the LLM context

## Evidence required
A finding is ONLY valid if backed by one of:
- A `bandit` hit (B307 eval, B602 subprocess shell=True, B603 subprocess without shell)
- A `semgrep` match on injection patterns
- A successful red-team trajectory where injected content changed agent behavior

No evidence → finding must be dropped by the Adjudicator.

## Remediation patterns
- Use structured tool I/O — never concatenate raw tool output into prompts
- Quarantine untrusted spans with XML delimiters: `<tool_result>...</tool_result>`
- Replace `eval()` with `ast.literal_eval()` for data, or remove entirely
- Set `shell=False` on all subprocess calls; pass args as a list
- Add input validation layer before any user content reaches tool calls