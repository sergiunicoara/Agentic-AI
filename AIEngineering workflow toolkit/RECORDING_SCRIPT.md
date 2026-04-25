# Recording Script — AI Engineering Workflow Toolkit
### Innovorg AI & Automation Developer · Screen Share · ~25 minutes

---

## Pre-recording checklist

- [ ] Terminal open in `AIEngineering workflow toolkit/`
- [ ] Browser at `http://localhost:8000` (run `python main.py ui` first)
- [ ] VS Code open with the project
- [ ] Loom recording ready, 1080p, mic tested
- [ ] `.env` with `ANTHROPIC_API_KEY` set (server needs it)
- [ ] `python main.py ui` running in background terminal tab

---

## SECTION 1 — Feature Request
**Time: 0:00–2:30 | Target: 2.5 min**

### What to show
Open VS Code. Have `AGENTS.md` and `README.md` side by side. No code yet.

### What to say

> "I'm going to walk you through one feature end-to-end — the entire AI Engineering Workflow Toolkit — treating it as a feature request delivered to me.
>
> The problem statement: AI code review tools hallucinate. An LLM asked to review a diff will confidently report findings it invented — missing docstrings that aren't missing, security issues with no basis in the actual code. The root cause isn't the prompt, it's the architecture. There's no mechanism forcing the model to consult real evidence before forming a verdict.
>
> The feature request is: build a governed code review pipeline where every LLM verdict must be grounded in deterministic tool output before any judgement occurs — enforced at the design level, not the prompt level.
>
> I captured this in `AGENTS.md` — this is the operating contract for every agent in this repository. It defines what agents are allowed to do, what tools they must consult first, and what evidence fields are mandatory on every finding."

**→ Switch to `AGENTS.md`, scroll through it briefly.**

> "This file acts as the feature spec and the governance layer at the same time. Before I wrote a single line of implementation, I had to commit to these constraints. That's an AI-first workflow — the spec itself is machine-readable and enforced at runtime."

---

## SECTION 2 — Architecture & Planning
**Time: 2:30–7:30 | Target: 5 min**

### What to show
`README.md` open, scrolled to the architecture diagram. Then switch to VS Code file tree showing the 5 layer directories.

### What to say

> "Let me walk you through the architecture before we look at code, because the structure is the most important design decision here."

**→ Show the ASCII architecture diagram in README.**

> "Five layers. Each one has a single responsibility and can only communicate downstream.
>
> **Layer 1** is the repository interface — versioned skill files in markdown that any agent in this repo loads at startup. These are the domain knowledge bases: OWASP security rules, SOLID architecture principles, linter-grounded style standards. They're versioned so you can A/B test skills and regression-test changes.
>
> **Layer 2** is the orchestrator. Its only job is coordination — it loads skills, calls the MCP tools, then fans out to three subagents in parallel. It makes zero quality judgements. That's intentional.
>
> **Layer 3a** is where things get interesting. This is a custom MCP server — Model Context Protocol — that exposes real developer tooling to Claude Code: ruff for linting, mypy for type checking, bandit for security scanning. These are deterministic tools. They produce verifiable, structured output. This is the architectural guarantee: before any LLM sees the diff, the deterministic tools have already run."

**→ Open `mcp_server/server.py`, scroll to show the three tool functions.**

> "Every tool returns a structured JSON dict — findings with file, line, rule, severity. This becomes the grounding evidence that all downstream agents must cite.
>
> **Layer 3b** — three specialised subagents running in parallel. Security, architecture, style. Each one receives the diff AND the full MCP tool output. The sequencing matters: tool output first, then LLM reasoning. Not the other way around.
>
> **Layer 4** — the review agent. It operates independently, receives only the merged subagent verdicts, validates that every single finding has a traceable `evidence` field quoting tool output or a diff line verbatim. Findings without evidence are suppressed and logged. This is where hallucinations get filtered out — structurally, not by hoping the prompt works.
>
> **Layer 5** — evaluation and observability. LLM-as-judge harness with a golden dataset, OTel spans on every pipeline run, and a regression threshold of 4.0/5.0. If a skill change drops accuracy, the eval catches it before it ships."

**→ Switch back to VS Code file tree showing the 5 directories.**

> "One design decision I want to highlight: I deliberately chose not to use a general-purpose agent framework here. No LangChain, no CrewAI. The pipeline is hand-rolled asyncio with explicit sequencing. When you're building something where the sequencing constraint IS the product — tools must run before LLMs — a framework that hides that sequencing is a liability."

---

## SECTION 3 — Implementation
**Time: 7:30–17:00 | Target: 9.5 min**

### Part A: Backend code walkthrough (5 min)

**→ Open `orchestrator/agent.py`**

> "Here's the orchestrator. The `run()` method is the pipeline entry point. Notice the `on_progress` callback parameter — this is how we get real-time WebSocket events to the frontend without coupling the pipeline logic to HTTP. The orchestrator doesn't know it's running behind a web server. It just calls the callback at each layer transition."

**→ Scroll to `_run_mcp_tools`, point at `asyncio.gather` and `_run_and_notify`.**

> "Tools run in parallel — asyncio.gather on three threads. Each tool notifies the frontend as soon as it completes, so you see results appearing live. I wrapped each tool call in `_run_and_notify` — that's the pattern that keeps progress reporting decoupled from business logic."

**→ Open `subagents/base.py`, scroll to `_build_system_prompt`**

> "Every subagent has a hard constraint baked into its system prompt: evidence is mandatory. If a finding doesn't have a traceable evidence field, the review agent will suppress it. The architecture makes hallucination expensive — the LLM has to do extra work to hallucinate past the traceability check."

**→ Open `review_agent/agent.py`, show the `_DISPOSITION_SCHEMA` tool definition**

> "The review agent uses forced tool use — `tool_choice: tool` — which means it cannot produce prose outside the structured schema. The output is always a typed `ReviewDisposition`. That's what goes into the database and what the frontend renders."

### Part B: Live demo (4.5 min)

**→ Switch to browser at `http://localhost:8000`**

> "Now let me show this running. This is the web UI I built on top of the pipeline — FastAPI backend, React frontend, WebSocket for live progress."

**→ Dashboard page**

> "Dashboard shows historical reviews, stats, and the latest eval regression score. We'll come back to that."

**→ Click 'New Review'**

> "I'm going to submit a diff. I've got a pre-built example — let me click 'Load example'. This diff adds an authentication function with several deliberate issues: a hardcoded secret key, SQL injection via f-string interpolation, MD5 password hashing, and no type annotations."

**→ Click 'Load example', show the diff in the textarea**

> "You can see it's a realistic-looking authentication module. Let me submit it and watch the pipeline run."

**→ Click 'Run Review', wait for redirect to Review Detail page**

> "Watch the pipeline visualization. Layer 1 — skills loaded. Layer 2 — orchestrator routing. Layer 3a — three tools running in parallel. You can see ruff, mypy, and bandit completing as their results come in..."

**→ Wait for Layer 3b to start — point at the three subagent badges**

> "Layer 3b — three subagents running simultaneously. Each one only reports findings grounded in tool output. The security agent sees bandit's output before forming any verdict."

**→ Wait for Layer 4 and verdict**

> "Layer 4 — review agent validating traceability and producing the final disposition. And there it is: Request Changes."

**→ Scroll down to findings, expand one finding card**

> "Three findings, all traceable. Look at this one — bandit B105, hardcoded password string. The evidence field quotes the bandit output verbatim. That's the architectural guarantee: you can audit every finding back to a tool result."

**→ Expand a security finding showing SQL injection**

> "SQL injection via f-string — bandit B608, high severity. File, line number, exact evidence, concrete suggestion. This is what actionable AI review looks like."

---

## SECTION 4 — Testing & Quality
**Time: 17:00–20:30 | Target: 3.5 min**

### What to show
Terminal. Open `eval/golden_dataset.json`. Run eval harness.

### What to say

**→ Open `eval/golden_dataset.json` in VS Code, show a case**

> "Testing this kind of system is non-trivial because the output is probabilistic. I built an LLM-as-judge evaluation harness with a golden dataset — 15 hand-crafted test cases covering the range of review scenarios: clean diffs, security-only issues, architecture violations, partial code snippets.
>
> Each golden case defines the expected verdict, required findings that must appear, and forbidden verdicts. The judge scores each pipeline output on three dimensions: traceability — are evidence fields present and valid? Accuracy — did it catch the right issues without hallucinating? Actionability — are findings specific, line-referenced, and fixable?"

**→ Switch to terminal, run:**
```bash
python main.py eval --case GC-001 --verbose
```

> "Let me run a single case to show the output format..."

**→ Wait for result, point at the scores**

> "4.7 out of 5. Traceability, accuracy, actionability scores. The regression threshold is 4.0 — anything below that and the pipeline is considered degraded."

**→ Open `eval/regression_log.jsonl`**

> "Every eval run appends to the regression log. This closes the feedback loop — when I change a skill file or update a prompt, I run the full 15-case eval and check the composite score before committing. That's model lifecycle management applied to a production agentic system, not an experiment."

---

## SECTION 5 — Deployment
**Time: 20:30–22:30 | Target: 2 min**

### What to show
Terminal + `pyproject.toml` + browser API docs.

### What to say

**→ Open `pyproject.toml`**

> "Deployment is intentionally simple. The project is packaged with setuptools — `pip install -e .` gets you the CLI and all dependencies. For the web UI layer I added an optional extras group — `pip install '.[ui]'` adds FastAPI and uvicorn."

**→ Show terminal, demonstrate the CLI**

```bash
python main.py --help
```

> "Four commands: `review` for CLI-driven reviews, `eval` for the harness, `serve` to start the MCP server for Claude Code integration, and `ui` to start the web server."

**→ Show that the server is running, open browser to `/api/docs`**

> "The FastAPI backend auto-generates OpenAPI docs — every endpoint documented, request and response schemas validated by Pydantic. This is production-grade API design, not a prototype.
>
> In a real deployment you'd put this behind nginx, containerise with Docker, and connect the OTel exporter to your observability stack. The instrumentation is already there — every pipeline run emits spans."

---

## SECTION 6 — AI/ML Deep Dive
**Time: 22:30–27:00 | Target: 4.5 min**

### What to show
Claude Code (open terminal in VS Code), `.claude/hooks/`, `skills/v1/`, `AGENTS.md`.

### What to say

**→ Open Claude Code terminal in VS Code**

> "I want to show you how I actually use AI tools in my development workflow — not just the product but the process.
>
> I use Claude Code as my primary AI coding assistant. Everything I built here was built with it. But more importantly, this project itself IS an AI coding infrastructure project. Let me show you the meta-layer."

**→ Open `.claude/hooks/pre_tool_use.py`**

> "I've got lifecycle hooks configured in Claude Code. This pre-tool-use hook intercepts every git commit in this repository and queues the diff for automated review. So whenever I commit code, the 5-layer pipeline reviews it automatically. The tooling reviews its own changes.
>
> This is an AI-first development workflow — not just 'I use an AI assistant to write code faster', but 'I've instrumented my development environment to provide AI-governed quality gates on every change.'"

**→ Open `skills/v1/security_review.md`**

> "The skill files are the most important artefact in this project for an AI engineering perspective. They're structured markdown documents that encode domain expertise — OWASP rules, SOLID principles, style standards — in a format that's both human-readable and machine-consumable.
>
> When I want to update what the security agent knows, I edit this file and run the eval harness. If the score holds above 4.0, the change ships. That's the full model lifecycle: edit skill → evaluate → regress or ship. No model training, no fine-tuning — just structured prompting with deterministic evaluation."

**→ Back to `AGENTS.md`**

> "And `AGENTS.md` is the governance layer. Any agent operating in this repository — Claude Code, subagents, the review agent — reads this file and operates within its constraints. It defines tool sequencing, evidence requirements, scope boundaries. It's the equivalent of a system prompt for the entire repository, not just one conversation.
>
> The key insight I want to leave you with: AI-first development isn't about using Claude to write more code faster. It's about designing systems where AI reasoning is structurally constrained by verifiable evidence. That's what separates reliable agentic AI from impressive demos."

---

## Closing (27:00–28:00)

**→ Return to browser dashboard, show it populated with the review from the demo**

> "To summarise: a 5-layer governed review pipeline, MCP server connecting Claude to real developer tooling, parallel specialised subagents required to cite evidence, an independent review agent that validates traceability, an LLM-as-judge eval harness, and OTel instrumentation on every run.
>
> All of this is in a single Python project, deployable with one command, and tested against a golden dataset on every change. That's the level of engineering rigour I bring to AI-automation work."

---

## Timing cheatsheet

| Section | Starts | Duration | Hard stop |
|---|---|---|---|
| Feature Request | 0:00 | 2:30 | 2:30 |
| Architecture & Planning | 2:30 | 5:00 | 7:30 |
| Implementation (code) | 7:30 | 5:00 | 12:30 |
| Implementation (demo) | 12:30 | 4:30 | 17:00 |
| Testing & Quality | 17:00 | 3:30 | 20:30 |
| Deployment | 20:30 | 2:00 | 22:30 |
| AI/ML Deep Dive | 22:30 | 4:30 | 27:00 |
| Closing | 27:00 | 1:00 | 28:00 |

**Total: ~28 minutes. If running long, cut Deployment to 1 min (just show `python main.py --help`).**

---

---

## BREAKTHROUGH MOMENT 1 — Live hook firing
**Insert at: end of Section 3 (Implementation), right after the demo**
**Time: ~16:30 | Duration: ~1 min**

### What to show
Have VS Code open to any Python file in the project (e.g. `mcp_server/server.py`).
The AIWT server must be running (`python main.py ui`).

### What to say

> "One more thing I want to show you — the hooks layer. Watch what happens when Claude Code writes a file."

**→ In VS Code, use Claude Code to make a one-line change to `mcp_server/server.py` and save it.**

> "The `post_tool_use.py` hook fires automatically. It generates a diff, detects the server is running, and POSTs it directly to the API."

**→ Switch to browser, hit refresh on Dashboard — the new review appears with an `AUTO` badge.**

> "The pipeline is now reviewing its own changes. The system governs itself. I didn't click anything — the commit trigger fired the hook, the hook hit the API, and the pipeline is running."

**→ Click the AUTO review to show it animating.**

---

## BREAKTHROUGH MOMENT 2 — Eval degradation demo
**Insert at: Section 4 (Testing & Quality), after first eval run**
**Time: ~19:00 | Duration: ~2 min**

### What to show
Terminal + `skills/v1/security_review.md` open in VS Code.

### What to say

> "Now let me show you what model lifecycle management actually looks like in practice — not as a concept."

**→ Open `skills/v1/security_review.md`, delete one paragraph (e.g. the section on hardcoded secrets). Save.**

> "I've just degraded the security skill. Let me run the eval with `--compare` to see the impact."

```bash
python main.py eval --compare
```

**→ Wait for results. Point at the red delta arrows.**

> "You can see specific cases that regressed — the delta arrows show exactly where accuracy dropped. That's the eval catching a skill change before it ships."

**→ Revert the skill file change. Run eval --compare again.**

> "Reverted. Scores recover. This is the full model lifecycle loop: change a skill, measure the impact, ship or revert. No guessing."

---

## BREAKTHROUGH MOMENT 3 — Time saved panel
**Insert at: Section 2 (Architecture) or closing**
**Time: ~6:30 or 27:30 | Duration: 30 sec**

### What to show
Browser → Dashboard, point at the "Est. Time Saved" stat card.

### What to say

> "The dashboard tracks estimated time saved. Assuming a 20-minute manual review, every automated review saves roughly 18 minutes. At scale — 50 PRs a week, that's 15 hours of senior developer time back per week. That's the business case for governed AI review."

---

## BREAKTHROUGH MOMENT 4 — OTel traces link
**Insert at: end of Section 3 (demo), after verdict appears**
**Time: ~17:00 | Duration: 30 sec**

### What to show
Review Detail page → click "View OTel Traces" button (top right) → agent-observability dashboard opens showing spans.

**Pre-requisite**: `agent-observability` stack must be running (`docker compose up` in the observability project).

### What to say

> "Every pipeline run emits OpenTelemetry spans. I can click here to jump directly into the observability dashboard and see the full trace — orchestrator, subagents, review agent — with timing and attributes. This is production-grade instrumentation, not a demo afterthought."

---

## BREAKTHROUGH MOMENT 5 — Domain pivot (closing, 30 sec)

**→ Return to Dashboard, point at the stats**

> "Everything you've seen is domain-agnostic — it works on any Python codebase. For Innovorg specifically, where you're shipping content generation pipelines, skill taxonomy APIs, and certification logic, I'd extend the skill library with domain-specific rules: validate that AI-generated learning content matches your taxonomy schema, flag certification boundary violations, enforce learning-path integrity constraints. Same pipeline, same eval harness, same OTel instrumentation — different skills."

---

## Key phrases to land

- *"Grounded in deterministic tool output before any LLM judgement occurs"*
- *"Enforced at the design level, not the prompt level"*
- *"The sequencing constraint IS the product"*
- *"Model lifecycle management applied to a production agentic system"*
- *"AGENTS.md is the governance layer for the entire repository"*
- *"The system governs itself"* (hook moment)
- *"Change a skill, measure the impact, ship or revert"* (eval degradation)
- *"15 hours of senior developer time back per week"* (business value)
