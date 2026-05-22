# Enterprise AI Incident Investigator — CLAUDE.md
# CCA-F Coverage: Domain 3.1 (CLAUDE.md hierarchy, @import, path-specific rules)

## Project Purpose
Multi-agent system that ingests logs/tickets/PDFs, decomposes the problem,
dispatches specialist subagents, and produces structured RCA reports.

## Architecture Overview
```
FastAPI backend
    └── Coordinator Agent (hub-and-spoke)
         ├── Retrieval Agent    (RAG over docs)
         ├── Log Analysis Agent (parse + correlate logs)
         ├── Code Analysis Agent(inspect repos)
         └── Report Generator   (structured JSON → RCA)
              └── MCP Servers: filesystem / github / postgres
```

## Stack
- Python 3.12, uv (NOT pip install — always use `uv pip install`)
- FastAPI + Pydantic v2
- Anthropic SDK (claude-sonnet-4-6 default, claude-haiku-4-5-20251001 for cheap tasks)
- MCP servers: custom Python (mcp SDK)
- Postgres (asyncpg), Redis (escalation queue)

## @import path rules — modular CLAUDE.md hierarchy
@.claude/rules/agents.md
@.claude/rules/mcp.md
@.claude/rules/api.md

## Configuration Hierarchy (exam critical — D3.1)
# NEVER put team standards in ~/.claude/settings.json (user level)
# Team standards → .claude/settings.json (project level, committed)
# Personal prefs only → ~/.claude/settings.json

## Always
- Use `uv pip install`, never `pip install`
- All agent outputs validate against Pydantic schemas before returning
- Structured errors include: error_type, source, recoverable, context
- Every subagent call passes explicit context (never assume inherited state)
- Tool descriptions must be precise: verb + noun + boundary (no vague descriptions)

## Never
- Silently swallow errors — always propagate with structured context
- Use sentiment as a proxy for confidence — use explicit numeric thresholds
- Mix orchestrator logic into subagent prompts
- Put team-wide rules in user-level settings (~/.claude/)

## Stop Reason Handling (D1.1 — exam critical)
All agentic loops MUST check stop_reason before proceeding:
- "tool_use"    → execute tool, append result, continue loop
- "end_turn"    → extract final answer, break
- "max_tokens"  → summarize progress, continue with context compaction
- "stop_sequence" → treat as structured signal (e.g. ESCALATE, DONE)

## Escalation Triggers (D5.2)
Escalate to human review when:
- confidence < 0.65 (numeric threshold, NOT "low confidence" vagueness)
- conflicting evidence from ≥2 sources with no resolution
- error_type == "permission" or "business_rule"
- stop_reason == "max_tokens" after 3 compaction attempts

## Token Budget
- Coordinator: 8192 max tokens
- Subagents: 4096 max tokens (haiku for retrieval, sonnet for analysis)
- Preserve transactional facts before summarization (D5.1)

## Running
```bash
# Install
uv pip install -e ".[dev]"

# MCP servers (run each in separate terminal or via docker-compose)
python -m mcp.servers.filesystem_server
python -m mcp.servers.github_server
python -m mcp.servers.postgres_server

# API
uvicorn api.app:app --reload

# Batch processing
python -m api.batch --input data/tickets.jsonl

# Evals
python evaluation/judge.py --dataset evaluation/golden_dataset.jsonl
```

## Plan Mode Usage (D3.4)
Use plan mode for:
- Multi-file refactors touching >3 files
- New agent or MCP server additions
- Schema changes that affect validation
Use direct execution for: single-file edits, adding tests, doc updates
