# Anti-Pattern Lab
# CCA-F: The 5 production failures the exam tests directly

Each file shows the WRONG pattern, explains why it fails, then shows the fix.
Study these — the exam presents wrong patterns and asks you to identify the issue.

## The 5 Failures

| File | Pattern | Domain | Exam trap |
|------|---------|--------|-----------|
| `01_vague_tool_descriptions.py` | Vague tool descriptions | D2.1 | Causes misrouting |
| `02_missing_subagent_context.py` | Implicit subagent context | D1.3 | Silent wrong results |
| `03_wrong_config_level.md` | Team standards in user settings | D3.1 | Team settings overridden |
| `04_vague_confidence_threshold.py` | String-based confidence | D5.2 | False positive escalations |
| `05_progressive_summarization_loss.py` | Summarization without fact preservation | D5.1 | Facts silently lost |

## How to use this lab

For each file:
1. Read the BAD version and understand WHY it fails
2. Run the demo if it has one
3. Read the GOOD version
4. Add to your exam mental model: "If I see X, the answer is Y"
