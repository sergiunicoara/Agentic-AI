# Enterprise AI Incident Investigator
### CCA-F (Claude Certified Architect — Foundations) Certification Project

Every file in this repo maps to specific exam sub-objectives. Build it week by week.

---

## CCA-F Exam Coverage Map

| Exam Sub-Objective | File(s) | Week |
|---|---|---|
| **D1.1** Agentic loop, stop_reason | `agents/loop.py` | 2 |
| **D1.2** Hub-and-spoke orchestration | `agents/coordinator.py` | 3 |
| **D1.3** Explicit subagent context | `agents/subagents/*.py`, `anti_patterns/02_*` | 3 |
| **D1.4** Programmatic vs prompt enforcement | `.claude/hooks/pre_tool_use.py` | 2 |
| **D1.5** Pre/PostToolUse hooks | `.claude/hooks/pre_tool_use.py`, `post_tool_use.py` | 2 |
| **D1.6** Task decomposition (adaptive vs fixed) | `agents/decomposer.py` | 3 |
| **D1.7** Session management, fork_session | `agents/session_manager.py` | 5 |
| **D2.1** Tool description design | `mcp/servers/filesystem_server.py`, `anti_patterns/01_*` | 4 |
| **D2.2** Structured MCP error responses | `mcp/errors.py`, `mcp/servers/*.py` | 4 |
| **D2.3** Tool distribution, tool_choice | `agents/decomposer.py`, `anti_patterns/01_*` | 4 |
| **D2.4** MCP server config (.mcp.json) | `.mcp.json`, `mcp/servers/*.py` | 4 |
| **D2.5** Built-in tools (Grep, Glob, Read) | `agents/subagents/log_analysis.py`, `code_analysis.py` | 4 |
| **D3.1** CLAUDE.md hierarchy, @import | `CLAUDE.md`, `anti_patterns/03_*` | 1 |
| **D3.2** Custom commands, skills | `.claude/commands/*.md` | 1 |
| **D3.3** Path-specific rules (glob frontmatter) | `.claude/rules/*.md` | 1 |
| **D3.4** Plan mode vs direct execution | `CLAUDE.md` (documented) | 1 |
| **D3.5** Iterative refinement, few-shot iteration | `agents/validator.py`, `prompts/few_shot.py` | 5 |
| **D3.6** CI/CD integration, -p flag | `.github/workflows/claude-review.yml` | 6 |
| **D4.1** Explicit criteria design | `agents/subagents/report_generator.py`, `prompts/few_shot.py` | 5 |
| **D4.2** Few-shot prompting | `agents/subagents/report_generator.py`, `prompts/few_shot.py` | 5 |
| **D4.3** Structured output via tool_choice | `agents/decomposer.py`, `agents/subagents/report_generator.py` | 5 |
| **D4.4** Validation + retry-with-feedback | `agents/validator.py` | 5 |
| **D4.5** Message Batches API (50% cost savings) | `api/batch.py` | 1 |
| **D4.6** Multi-instance review | `agents/subagents/report_generator.py`, `.claude/commands/review-pr.md` | 5 |
| **D5.1** Context preservation, transactional facts | `agents/context_manager.py`, `anti_patterns/05_*` | 6 |
| **D5.2** Escalation, numeric thresholds | `agents/escalation.py`, `anti_patterns/04_*` | 6 |
| **D5.3** Error propagation in multi-agent | `agents/error_handler.py`, `schemas/rca_output.py` | 6 |
| **D5.4** Large codebase exploration | `agents/subagents/code_analysis.py` | 4 |
| **D5.5** Human review, stratified sampling | `evaluation/judge.py`, `api/human_review.py` | 6 |
| **D5.6** Information provenance | `agents/provenance.py` | 6 |

---

## 6-Week Build Plan

### Week 1 — Claude Code Config + Structured Output Foundation
**Goal**: Everything configured correctly from day 1.

Files to create first:
- [ ] `CLAUDE.md` — project rules, @import, hierarchy
- [ ] `.claude/settings.json` — project-level (team standards)
- [ ] `.claude/rules/*.md` — path-specific rules with glob frontmatter
- [ ] `.claude/commands/*.md` — custom slash commands
- [ ] `schemas/rca_output.py` — Pydantic + JSON schema
- [ ] `api/batch.py` — Message Batches API

**What you learn**: CLAUDE.md hierarchy, config levels, structured output,
batch processing. Exam domains: **D3.1, D3.2, D3.3, D4.3, D4.5**.

Exam drill: read `anti_patterns/03_wrong_config_level.md`.

---

### Week 2 — Agentic Loop + Hooks
**Goal**: Correct stop_reason handling; policy in hooks not prompts.

Files:
- [ ] `agents/loop.py` — stop_reason: end_turn / tool_use / max_tokens
- [ ] `.claude/hooks/pre_tool_use.py` — guardrails
- [ ] `.claude/hooks/post_tool_use.py` — normalization
- [ ] `tests/test_loop.py`

**What you learn**: The agentic loop lifecycle, hooks as programmatic enforcement.
Exam domains: **D1.1, D1.4, D1.5**.

Exam drill: can you recite all 4 stop_reason values and what to do for each?

---

### Week 3 — Multi-Agent Architecture
**Goal**: Coordinator + subagents with explicit context passing.

Files:
- [ ] `agents/coordinator.py` — hub-and-spoke, parallel dispatch
- [ ] `agents/decomposer.py` — adaptive decomposition
- [ ] `agents/subagents/retrieval.py` — explicit context receive
- [ ] `agents/subagents/log_analysis.py`
- [ ] `agents/subagents/code_analysis.py`
- [ ] `agents/subagents/report_generator.py`

**Deliberate break/fix exercise**:
1. Build coordinator that passes NO context to subagents → observe garbage output
2. Add explicit context → observe improvement
3. Write down EXACTLY what changed and why

Exam domains: **D1.2, D1.3, D1.6**.
Exam drill: read `anti_patterns/02_missing_subagent_context.py`.

---

### Week 4 — MCP Integration
**Goal**: 3 MCP servers with precise tool descriptions.

Files:
- [ ] `mcp/errors.py` — isError pattern, 4 error categories
- [ ] `mcp/servers/filesystem_server.py`
- [ ] `mcp/servers/postgres_server.py`
- [ ] `mcp/servers/github_server.py`
- [ ] `.mcp.json` — project-level config
- [ ] `tests/test_mcp_errors.py`

**Tool description lab** (most-overlooked exam area):
1. Write a bad tool description for each server tool
2. Observe what calls Claude makes
3. Rewrite with VERB+NOUN+BOUNDARY+CONSTRAINTS
4. Compare — write down why the good version works better

Exam domains: **D2.1, D2.2, D2.3, D2.4, D2.5**.
Exam drill: read `anti_patterns/01_vague_tool_descriptions.py`.

---

### Week 5 — Prompt Engineering + Context Engineering
**Goal**: Few-shot prompting, validation retries, session management, provenance.

Files:
- [ ] `prompts/few_shot.py` — few-shot examples
- [ ] `agents/validator.py` — retry-with-error-feedback
- [ ] `agents/session_manager.py` — named sessions, fork
- [ ] `agents/provenance.py` — source attribution
- [ ] `agents/escalation.py` — numeric thresholds
- [ ] `tests/test_structured_output.py`

Exam domains: **D4.1, D4.2, D4.4, D4.6, D1.7, D5.2, D5.6**.

---

### Week 6 — Reliability + CI/CD + Evals
**Goal**: Full reliability layer; CI/CD scenario; golden dataset.

Files:
- [ ] `agents/context_manager.py` — progressive summarization + fact preservation
- [ ] `agents/error_handler.py` — structured error propagation
- [ ] `api/human_review.py` — stratified priority routing
- [ ] `evaluation/golden_dataset.jsonl` + `evaluation/judge.py`
- [ ] `.github/workflows/claude-review.yml`

**Anti-pattern lab** (final week):
Go through each file in `anti_patterns/` in order.
For each: implement the bad pattern, run it, observe failure, apply the fix.
Write one sentence per anti-pattern: "This fails because ___."

Exam domains: **D5.1, D5.3, D5.5, D3.6**.

---

## Quick Reference: The 5 Production Failures

| # | Failure | Fix | Domain |
|---|---------|-----|--------|
| 1 | Vague tool descriptions | VERB+NOUN+BOUNDARY+CONSTRAINTS | D2.1 |
| 2 | Subagent context not passed | Explicit context dict every call | D1.3 |
| 3 | Team standards in user-level config | Move to `.claude/settings.json` | D3.1 |
| 4 | String-based confidence | Numeric threshold (< 0.65) | D5.2 |
| 5 | Progressive summarization loss | Extract facts before compaction | D5.1 |

## Running

```bash
# Setup (uv only — never pip install)
uv pip install -e ".[dev]"

# MCP servers
python -m mcp.servers.filesystem_server &
python -m mcp.servers.postgres_server &
python -m mcp.servers.github_server &

# API
uvicorn api.app:app --reload

# Claude Code commands
/analyze-ticket INC-2047
/review-pr 42
/batch-process data/tickets.jsonl
/run-evals

# Direct
python -m agents.coordinator analyze "DB connection pool exhausted..."
python -m api.batch --input data/tickets.jsonl
python evaluation/judge.py --dataset evaluation/golden_dataset.jsonl

# Tests
pytest tests/ -v
```
