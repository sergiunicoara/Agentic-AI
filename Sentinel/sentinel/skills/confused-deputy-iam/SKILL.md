---
name: confused-deputy-iam
description: Detect confused deputy vulnerabilities where an agent forwards credentials or acts on behalf of a caller without verifying intent.
triggers: [credential_forwarding, token_passthrough, api_key_in_tool, iam_role]
pillar: 5
---

## What to look for
- Agent forwards caller's auth token to downstream services without validation
- API keys or secrets passed as tool arguments rather than injected at runtime
- Agent has write/delete permissions but the task only requires read
- No scope check before high-privilege actions (delete, write, deploy)
- Credentials stored in session state accessible to all agents in pipeline

## Evidence required
A finding is ONLY valid if backed by one of:
- A `bandit` hit (B106 hardcoded password, B107 hardcoded password funcarg)
- A `semgrep` match on credential patterns
- Static analysis showing credentials in function arguments or string literals

No evidence → finding must be dropped by the Adjudicator.

## Remediation patterns
- Inject credentials at the infrastructure level, not through agent arguments
- Apply principle of least privilege — scope each agent's IAM role to minimum needed
- Add explicit scope validation before any destructive action
- Never store credentials in LLM-visible session state
- Use short-lived tokens with automatic expiry