# AI Engineering Workflow Toolkit — AGENTS.md

This file defines the operating constraints, roles, and interaction protocols for every agent
that runs within this repository. All agents MUST read and honour these constraints before
acting.

---

## Repository Purpose

This toolkit implements governed code review infrastructure. Every code change that enters
this repository passes through a five-layer pipeline that grounds AI reasoning in deterministic
tool output before any LLM judgement occurs.

---

## Agent Roles

### Orchestrator Agent (`orchestrator/agent.py`)
- **Responsibility**: Coordination only. Routes diffs to tools and subagents. Never reasons
  about code quality directly.
- **Inputs**: Raw diff, loaded skills, repository root path.
- **Outputs**: Merged dict containing `diff`, `tool_output`, `subagent_verdicts`, `skills_used`.
- **Constraints**: Must not produce any code quality judgement. Must load skills before routing.

### Security Subagent (`subagents/security_agent.py`)
- **Responsibility**: Security-focused review only (OWASP Top 10, injection, secrets, auth).
- **Inputs**: Diff + MCP tool output (linter, type checker, security scanner results).
- **Outputs**: Structured `SubagentVerdict` with findings traceable to tool results or diff lines.
- **Constraints**: Every finding MUST cite either a `tool_finding_id` or a `diff_line` reference.
  Must not comment on architecture or style.

### Architecture Subagent (`subagents/architecture_agent.py`)
- **Responsibility**: Structural and design review only (SOLID, coupling, dependency direction,
  layer violations, interface boundaries).
- **Inputs**: Diff + MCP tool output.
- **Outputs**: Structured `SubagentVerdict`.
- **Constraints**: Every finding MUST be traceable. Must not comment on security or style.

### Style Subagent (`subagents/style_agent.py`)
- **Responsibility**: Code style, naming, documentation, and consistency review.
- **Inputs**: Diff + MCP tool output (linter findings are primary evidence).
- **Outputs**: Structured `SubagentVerdict`.
- **Constraints**: Every finding MUST be traceable. Must not comment on security or architecture.

### Review Agent (`review_agent/agent.py`)
- **Responsibility**: Final disposition. Validates traceability of all subagent findings.
  Produces the authoritative review with line-level annotations.
- **Inputs**: Merged orchestrator output (diff + tool_output + subagent_verdicts).
- **Outputs**: `ReviewDisposition` — one of `approve`, `request_changes`, `comment` — with
  ranked, line-level annotations.
- **Constraints**: MUST reject any finding that cannot be traced to a tool result or diff line.
  Operates independently — does not re-query subagents.

---

## Skill Loading Protocol

1. The orchestrator reads `skills/registry.json` to identify applicable skills for the diff.
2. Skills are selected based on file extensions and detected change types.
3. Loaded skill content is injected into each subagent's system prompt as `<skill>` blocks.
4. Skills are versioned. Always load from the version pinned in `registry.json`.

---

## Output Format Contract

All agent outputs MUST conform to the Pydantic models defined in each module. Unstructured
prose responses will be rejected by the pipeline.

```
Finding {
  id: str           # unique within session
  file: str         # relative file path
  line: int | null  # specific line number or null for file-level
  severity: "error" | "warning" | "info"
  rule: str         # rule identifier (e.g. "bandit/B101", "ruff/E501", "agent/SEC-001")
  message: str      # concise, actionable description
  evidence: str     # direct quote from tool output or diff that grounds this finding
}
```

---

## Traceability Requirement

**This is the non-negotiable architectural constraint of this system.**

Every agent finding must have a populated `evidence` field that directly quotes either:
1. A tool result (linter output, type error, bandit finding), or
2. A specific line from the diff (quoted verbatim).

Findings without traceable evidence are suppressed by the review agent and logged as
`untraceable` in the regression log.

---

## Lifecycle Hooks

Hooks in `.claude/settings.json` intercept Claude Code tool events:

| Hook Event       | Trigger                    | Action                                    |
|------------------|----------------------------|-------------------------------------------|
| PostToolUse      | After Write or Edit tool   | Extract changed file path, queue review   |
| PreToolUse       | Before Bash (git commit)   | Capture staged diff, run full pipeline    |

Hook scripts in `.claude/hooks/` receive JSON on stdin from Claude Code and invoke the
orchestrator pipeline.

---

## Evaluation Contract

- The `eval/golden_dataset.json` contains the reference cases for this repository.
- Every skill or prompt change MUST be re-evaluated against the full golden dataset before
  being considered stable.
- Regression threshold: overall score must not drop below 4.0/5.0.
- Results are appended to `eval/regression_log.jsonl`.

---

## Environment Variables

| Variable              | Description                                     | Required |
|-----------------------|-------------------------------------------------|----------|
| `ANTHROPIC_API_KEY`   | Claude API key                                  | Yes      |
| `OTEL_EXPORTER_ENDPOINT` | OpenTelemetry gRPC endpoint (default: localhost:4317) | No |
| `REVIEW_MODEL`        | Override default review model                   | No       |
| `EVAL_MODEL`          | Override default eval judge model               | No       |
