---
# CCA-F D3.2 + D3.6: CI/CD-oriented custom command
description: "Review a PR for correctness, security, and agent pattern adherence"
context: fork
tools:
  - mcp__github__read_file
  - mcp__github__list_commits
  - Read
  - Bash
---

# /review-pr

Review a GitHub PR using a second independent Claude instance (D4.6 multi-instance review).

## Why second instance? (D4.6 exam concept)
Self-review has limitations — the same reasoning that produced the bug will miss it.
This command spawns a fresh Claude instance with only the diff as context.

## Usage
```
/review-pr <pr_number>
/review-pr <pr_number> --focus=security
/review-pr <pr_number> --focus=agent-patterns
```

## Checklist applied
- [ ] stop_reason handled for all cases
- [ ] Subagents receive explicit context (not assumed)
- [ ] Tool descriptions are precise (verb+noun+boundary)
- [ ] Errors are structured (error_type, source, recoverable)
- [ ] No team standards in user-level config
- [ ] Progressive summarization preserves transactional facts
- [ ] Confidence thresholds are numeric, not vague strings
- [ ] No `pip install` (must use `uv pip install`)

## Output
Structured review report → `.claude/reviews/pr_<number>_review.json`

## Steps
Run: `python -m agents.reviewer pr $ARGUMENTS`
