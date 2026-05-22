# CCA-F Repository Coverage Audit

Date checked: 2026-05-21

## Sources Used

- Anthropic announcement: Claude Certified Architect, Foundations is Anthropic's first technical certification for solution architects building production Claude applications.
  https://www.anthropic.com/news/claude-partner-network
- Anthropic Academy course pages used as primary curriculum signals:
  - Subagents: https://anthropic.skilljar.com/introduction-to-subagents
  - Agent Skills: https://anthropic.skilljar.com/introduction-to-agent-skills
- Anthropic docs used for implementation checks:
  - Stop reasons: https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons
  - Structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
  - Claude Code hooks: https://code.claude.com/docs/en/hooks
  - Claude Code MCP: https://code.claude.com/docs/en/mcp
- Secondary blueprint mirror used only where the official exam guide is not publicly readable without Skilljar access:
  https://claudecertifications.com/claude-certified-architect/exam-guide

## Executive Summary

The repository covers all five broad CCA-F domains and the six common scenario families:

- Agentic architecture and orchestration
- Tool design and MCP integration
- Claude Code configuration and workflows
- Prompt engineering and structured output
- Context management and reliability
- CI/CD, evaluation, and human review workflows

Readiness level: good training skeleton, not yet fully executable end to end in this local shell.

Main gaps:

1. `uv` is not available on PATH, so the documented setup/test path cannot run as written.
2. `pytest` is not installed in the active Python environment.
3. `agents/loop.py` teaches the classic four stop reasons, but current official API docs also call out `pause_turn`, `refusal`, and `model_context_window_exceeded`.
4. Structured output examples use forced `tool_choice`; current docs now also emphasize `output_config.format` JSON schemas and `strict: true` tool use.
5. Several subagent/tool executors are mocks, so the repo demonstrates the exam concepts but does not yet prove a live full investigation.

## Domain Coverage

| Domain | Requirement Theme | Repo Evidence | Status | Practice Path |
|---|---|---|---|---|
| D1 | Agentic architecture, loops, orchestration, subagents, sessions | `agents/loop.py`, `agents/coordinator.py`, `agents/decomposer.py`, `agents/session_manager.py`, `agents/subagents/*` | Covered, update stop reasons | Walk through `agents/loop.py`, then trace `CoordinatorAgent.investigate()` from decomposition to report |
| D2 | Tool design, MCP, tool boundaries, structured errors | `.mcp.json`, `mcp/errors.py`, `mcp/servers/*`, `.claude/rules/mcp.md` | Covered | Compare `anti_patterns/01_*` with `filesystem_server.py` tool descriptions |
| D3 | Claude Code config, commands, hooks, plan mode, CI/CD | `CLAUDE.md`, `.claude/settings.json`, `.claude/commands/*`, `.claude/hooks/*`, `.github/workflows/claude-review.yml` | Covered | Open `CLAUDE.md`, then inspect settings and one slash command |
| D4 | Criteria, few-shot, schemas, validation/retry, batch | `schemas/rca_output.py`, `prompts/few_shot.py`, `agents/validator.py`, `api/batch.py`, `agents/subagents/report_generator.py` | Covered, modernize structured-output API examples | Validate one good RCA and one bad RCA against `RCAOutput` |
| D5 | Context preservation, escalation, errors, evals, provenance | `agents/context_manager.py`, `agents/escalation.py`, `agents/error_handler.py`, `evaluation/judge.py`, `api/human_review.py`, `agents/provenance.py` | Covered | Run the anti-patterns for summarization loss, vague confidence, and empty-result vs access-error |

## Practical Walkthrough Order

Use this order when studying the repo. It follows how a real incident flows through the system.

1. Start with the contract:
   - `schemas/rca_output.py`
   - What to notice: required fields, `confidence` bounds, `escalation_reason` rule, evidence/provenance fields.

2. Run the agentic loop mentally:
   - `agents/loop.py`
   - What to notice: inspect `stop_reason`, execute tool calls, append `tool_result`, compact on token pressure, guard max iterations.
   - Update target: add handling for `pause_turn`, `refusal`, and `model_context_window_exceeded`.

3. Trace orchestration:
   - `agents/coordinator.py`
   - What to notice: adaptive decomposition, parallel independent agents, sequential report generation, explicit context construction.

4. Inspect tool and MCP design:
   - `.mcp.json`
   - `mcp/servers/filesystem_server.py`
   - `mcp/errors.py`
   - What to notice: project-scoped config, narrow tool set, precise descriptions, `isError` structured errors.

5. Study Claude Code workflow configuration:
   - `CLAUDE.md`
   - `.claude/settings.json`
   - `.claude/commands/analyze-ticket.md`
   - `.claude/hooks/pre_tool_use.py`
   - What to notice: project rules vs user preferences, hooks for deterministic policy, forked command contexts.

6. Practice structured output and retries:
   - `agents/subagents/report_generator.py`
   - `agents/validator.py`
   - `api/batch.py`
   - What to notice: few-shot examples, severity criteria, forced tool output, retry-with-feedback, batch polling.

7. Finish with reliability:
   - `agents/context_manager.py`
   - `agents/escalation.py`
   - `agents/error_handler.py`
   - `agents/provenance.py`
   - `evaluation/judge.py`
   - What to notice: fact preservation before summarization, numeric escalation thresholds, source attribution, stratified evaluation.

## Local Verification

Commands attempted:

```powershell
uv run pytest tests -v
python -m pytest tests -v
python -m py_compile agents\loop.py agents\coordinator.py agents\decomposer.py agents\validator.py agents\context_manager.py agents\escalation.py agents\error_handler.py agents\provenance.py agents\session_manager.py schemas\rca_output.py mcp\errors.py mcp\servers\filesystem_server.py api\batch.py api\app.py evaluation\judge.py
```

Results:

- `uv run pytest tests -v` could not run because `uv` is not on PATH.
- `python -m pytest tests -v` could not run because `pytest` is not installed in the active Python environment.
- `python -m py_compile ...` passed for the core Python modules listed above.

## High-Priority Next Improvements

1. Install or expose `uv`, then run the documented test command.
2. Add tests for `pause_turn`, `refusal`, and `model_context_window_exceeded`.
3. Add one modern structured-output example using `output_config.format` or SDK parsing with Pydantic.
4. Replace at least one mocked executor with a real local read/search path so the practical walkthrough can demonstrate actual data flow.
5. Add a small sample `data/` incident and a command that runs without an API key by using mocked model/tool responses.
