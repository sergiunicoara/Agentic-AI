# AI Engineering Workflow Toolkit
### Governed Code Review Infrastructure for Claude Code

A production-grade, repository-deployable infrastructure layer that enforces quality standards
on every code change by grounding AI reasoning in deterministic tool output before any LLM
judgement occurs.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — Repository Interface                                      │
│  AGENTS.md · skills/v1/ (versioned skill library) · .claude/hooks/  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  diff + loaded skills
┌──────────────────────────▼──────────────────────────────────────────┐
│  LAYER 2 — Orchestrator Agent                                        │
│  Coordinates: routes diff, triggers Layer 3 in parallel, merges     │
└──────┬───────────────────────────────────────────────────┬──────────┘
       │                                                   │
┌──────▼──────────────┐                    ┌──────────────▼──────────┐
│  LAYER 3a — MCP     │                    │  LAYER 3b — Subagents   │
│  Server             │  tool output ────► │  Security · Architecture│
│  Linter · Typer ·   │                    │  · Style                │
│  Security Scanner   │                    │  (parallel, grounded)   │
└─────────────────────┘                    └──────────────┬──────────┘
                                                          │ merged verdicts
┌─────────────────────────────────────────────────────────▼──────────┐
│  LAYER 4 — Review Agent                                             │
│  Validates traceability · Produces structured disposition            │
│  approve | request_changes | comment + ranked line annotations      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  LAYER 5 — Evaluation & Observability                                │
│  OTel spans → Agent Observability Dashboard                          │
│  LLM-as-judge harness · Golden dataset · Regression log             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ regression failures
                           └──► revise skills/hooks in Layer 1
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -e ".[dev]"
```

This also installs `ruff`, `mypy`, and `bandit` — the deterministic tools used by the MCP server.

### 2. Set environment variables

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OTEL_EXPORTER_ENDPOINT=localhost:4317  # optional, defaults to console
```

### 3. Review a diff

```bash
# Review current git staged diff
python main.py review

# Review a specific diff file
python main.py review --diff path/to/changes.patch

# Review a specific file
python main.py review --file src/my_module.py
```

### 4. Run evaluation harness

```bash
python main.py eval
```

### 5. Start MCP server (for Claude Code integration)

```bash
python main.py serve
```

---

## Layer Details

### Layer 1 — Repository Interface

| Component | Purpose |
|-----------|---------|
| `AGENTS.md` | Operating constraints for every agent in this repo |
| `skills/v1/security_review.md` | OWASP-grounded security review standards |
| `skills/v1/architecture_review.md` | SOLID and structural design standards |
| `skills/v1/style_review.md` | Naming, documentation, and consistency standards |
| `skills/registry.json` | Maps file extensions and change types to skill versions |
| `.claude/hooks/pre_tool_use.py` | Captures git commit diff, triggers pipeline |
| `.claude/hooks/post_tool_use.py` | Captures file writes, queues review |

### Layer 2 — Orchestrator Agent

Single responsibility: coordination. Loads skills, invokes the MCP server for deterministic
tool output, then passes that output to the three subagents in parallel. Merges all outputs
into a single consolidated input for the review agent.

Model: `claude-opus-4-6`

### Layer 3a — MCP Server

Deterministic tooling exposed via the Model Context Protocol:

| Tool | Implementation | Output |
|------|---------------|--------|
| `run_linter` | `ruff check` | JSON findings with file, line, rule, message |
| `run_type_checker` | `mypy` | JSON findings with file, line, error type |
| `run_security_scanner` | `bandit` | JSON findings with file, line, severity, CWE |

### Layer 3b — Specialised Subagents

Each subagent receives the diff AND the full MCP tool output before forming any judgement.
This sequencing is the architectural guarantee that grounds every LLM verdict in verifiable
evidence.

| Subagent | Domain | Model |
|----------|--------|-------|
| Security | OWASP Top 10, injection, secrets, auth | `claude-sonnet-4-6` |
| Architecture | SOLID, coupling, layer violations | `claude-sonnet-4-6` |
| Style | Naming, docs, linter rule adherence | `claude-sonnet-4-6` |

### Layer 4 — Review Agent

Operates independently. Receives only the merged verdicts and original diff. Validates that
every finding has a traceable evidence field. Produces a `ReviewDisposition` with:
- Overall verdict: `approve` / `request_changes` / `comment`
- Ranked findings sorted by severity
- Line-level annotations in diff format

Model: `claude-opus-4-6`

### Layer 5 — Evaluation & Observability

**OpenTelemetry**: Every pipeline run emits spans to the configured OTLP endpoint.
Integrates with the `agent-observability` dashboard in this workspace.

**Evaluation Harness**: `eval/harness.py` runs the full pipeline against `eval/golden_dataset.json`
and scores each output with an LLM-as-judge prompt. Results are appended to
`eval/regression_log.jsonl`.

**Regression threshold**: 4.0/5.0 average score across all golden cases.

---

## File Structure

```
AIEngineering workflow toolkit/
├── AGENTS.md                    # Layer 1: Agent operating constraints
├── README.md
├── pyproject.toml
├── main.py                      # CLI entry point
│
├── .claude/
│   ├── settings.json            # Hook configuration
│   └── hooks/
│       ├── pre_tool_use.py      # Pre-commit hook
│       └── post_tool_use.py     # Post-file-write hook
│
├── skills/                      # Layer 1: Versioned skill library
│   ├── registry.json
│   ├── loader.py
│   └── v1/
│       ├── security_review.md
│       ├── architecture_review.md
│       └── style_review.md
│
├── orchestrator/                # Layer 2
│   └── agent.py
│
├── mcp_server/                  # Layer 3a
│   └── server.py
│
├── subagents/                   # Layer 3b
│   ├── base.py
│   ├── security_agent.py
│   ├── architecture_agent.py
│   └── style_agent.py
│
├── review_agent/                # Layer 4
│   └── agent.py
│
├── observability/               # Layer 5
│   └── tracer.py
│
└── eval/                        # Layer 5
    ├── harness.py
    ├── judge.py
    ├── golden_dataset.json
    └── regression_log.jsonl     # auto-generated
```

---

## CV / Portfolio Description

**AI Engineering Workflow Toolkit — Governed Code Review Infrastructure for Claude Code**

A production-grade, repository-deployable infrastructure layer that enforces quality standards
on every code change by grounding AI reasoning in deterministic tool output before any LLM
judgement occurs.

The toolkit comprises five integrated layers: a versioned AGENTS.md skill library with lifecycle
hooks that standardise how agents operate within repositories; a custom MCP server connecting
Claude Code to real developer tooling — linter, type checker, and security scanner — as
structured, evidence-producing gates; a parallel subagent pipeline with three specialised
reviewers (security, architecture, style) each required to interpret deterministic tool output
before forming a verdict; an independent review agent that merges findings, validates
traceability, and produces a structured disposition with line-level annotations; and an
LLM-as-judge evaluation harness with a golden dataset and regression logging that closes the
feedback loop on every skill or prompt revision. All agent spans are instrumented with
OpenTelemetry and integrated with the Agent Observability Dashboard for live trace visibility.
