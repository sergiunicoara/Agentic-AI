---
name: prompt-injection-defense
description: Detects vulnerability to prompt injection attacks and evaluates system prompt isolation controls.
triggers:
  - prompt injection
  - jailbreak
  - system instruction
---

# Prompt Injection Defense

## What to look for
- System prompts that concatenate untrusted user input directly without sanitization or boundaries.
- Absence of system prompt protection/instructions.
- Over-reliance on LLM compliance without output parser checks.

## Evidence required
- Textual patterns matching string formatting or template interpolation in prompt generation.
- Dynamic red-team trajectory results showing prompt escape.

## Remediation patterns
- Use structured formats (e.g. chat messages API structure) rather than raw string interpolation.
- Enforce strict input delimiters (e.g. triple backticks, custom XML tags) and instruct the model to ignore formatting within those.
- Add downstream output sanitization and validation.
