# Recording Script — AI Engineering Workflow Toolkit
### Innovorg AI & Automation Developer · Screen Share · 28 min

---

## Pre-recording checklist

- [ ] `python main.py ui` running in a **background** terminal tab (server must be up for hook demo)
- [ ] `ANTHROPIC_API_KEY` exported in that terminal
- [ ] Browser open at `http://localhost:8000` — Dashboard visible
- [ ] VS Code open, project root loaded, file tree visible in sidebar
- [ ] Loom recording set to 1080p, mic level checked
- [ ] *(Optional — for OTel demo)* `agent-observability` stack running: `docker compose up`
- [ ] Practice the hook demo once: save a file, confirm `✓ Live review started` appears in terminal

---

## Timing overview

| # | Section | Start | Dur | End |
|---|---------|-------|-----|-----|
| 1 | Feature Request | 0:00 | 2:30 | 2:30 |
| 2 | Architecture & Planning | 2:30 | 4:00 | 6:30 |
| ⚡ | *Time Saved callout* | 6:30 | 0:30 | 7:00 |
| 3a | Implementation — Code | 7:00 | 5:00 | 12:00 |
| 3b | Implementation — Live demo | 12:00 | 4:00 | 16:00 |
| ⚡ | *Live hook firing* | 16:00 | 1:15 | 17:15 |
| ⚡ | *OTel traces* | 17:15 | 0:30 | 17:45 |
| 4a | Testing — Golden dataset | 17:45 | 1:15 | 19:00 |
| ⚡ | *Eval degradation* | 19:00 | 2:30 | 21:30 |
| 5 | Deployment | 21:30 | 1:30 | 23:00 |
| 6 | AI/ML Deep Dive | 23:00 | 4:00 | 27:00 |
| ⚡ | *Domain pivot + close* | 27:00 | 1:00 | 28:00 |

**If running long:** drop Section 5 (Deployment) entirely — `python main.py --help` is not a differentiator. That buys back 90 seconds.

---
---

## ⏱ 0:00 — SECTION 1: Feature Request
**Target: 2:30**

📌 **SCREEN:** VS Code — `AGENTS.md` and `README.md` open side by side. No code visible yet.

---

> "I'm going to walk you through this project end-to-end, treating it as a feature request that was delivered to me.
>
> The problem: AI code review tools hallucinate. An LLM asked to review a diff will confidently report findings it invented — missing docstrings that aren't missing, security issues with no basis in the actual code. The root cause isn't the prompt. It's the architecture. There's no mechanism forcing the model to consult real evidence before forming a verdict.
>
> The feature request: build a governed code review pipeline where every LLM verdict must be grounded in deterministic tool output before any judgement occurs — enforced at the design level, not the prompt level."

**→ Switch focus to `AGENTS.md`. Scroll slowly through it.**

> "I captured the entire requirement in `AGENTS.md`. This is the operating contract for every agent in this repository — what tools they must consult, what evidence fields are mandatory, what they're forbidden from doing. Before I wrote a single line of implementation, I committed to these constraints in writing.
>
> That's an AI-first workflow. The spec is machine-readable and enforced at runtime."

---

## ⏱ 2:30 — SECTION 2: Architecture & Planning
**Target: 4:00 → end at 6:30**

📌 **SCREEN:** `README.md` scrolled to the ASCII architecture diagram.

---

> "Let me walk through the architecture before any code, because the structure is the most important design decision."

**→ Point at the diagram layer by layer as you speak.**

> "Five layers, single responsibility each, communication flows only downstream.
>
> **Layer 1** — versioned skill files in markdown. OWASP security rules, SOLID architecture principles, linter-grounded style standards. They're versioned so you can A/B test skills and regression-test changes before shipping.
>
> **Layer 2** — the orchestrator. Coordination only. Loads skills, calls the MCP tools, fans out to three subagents in parallel. Zero quality judgement. That's intentional.
>
> **Layer 3a** — a custom MCP server that exposes real developer tooling: ruff for linting, mypy for type checking, bandit for security scanning. These are deterministic tools. They produce verifiable, structured JSON. This is the architectural guarantee: before any LLM sees the diff, the tools have already run."

**→ Open `mcp_server/server.py`. Scroll to show `run_linter`, `run_type_checker`, `run_security_scanner`.**

> "Each tool returns findings with file, line, rule, severity. This JSON becomes the mandatory grounding evidence.
>
> **Layer 3b** — three specialised subagents in parallel: security, architecture, style. Each one receives the diff AND the full tool output. Sequencing matters: tool output first, LLM reasoning second. Never the other way around.
>
> **Layer 4** — the review agent. Validates that every finding has a traceable evidence field quoting tool output or a diff line verbatim. Findings without evidence are suppressed and counted. Hallucination filtered structurally, not by prompt engineering.
>
> **Layer 5** — eval harness with a golden dataset, OTel spans on every run, regression threshold 4.0/5.0."

**→ Switch to VS Code file tree. Show the 5 directories: `orchestrator/`, `mcp_server/`, `subagents/`, `review_agent/`, `eval/`.**

> "One deliberate decision: no agent framework. No LangChain, no CrewAI. Hand-rolled asyncio with explicit sequencing. When the sequencing constraint IS the product — tools must run before LLMs — a framework that abstracts that away is a liability, not an asset."

---

> ### ⚡ TIME SAVED — 30 seconds
> **⏱ ~6:30**

**→ Switch to browser → Dashboard. Point at the "Est. Time Saved" stat card (top right of the four cards).**

> "The dashboard tracks this in real time. Assuming a 20-minute manual review, every automated pipeline run saves roughly 18 minutes. At 50 PRs a week that's 15 hours of senior developer time back — per week. That's the business case, not the technology case."

---

## ⏱ 7:00 — SECTION 3a: Implementation — Code Walkthrough
**Target: 5:00 → end at 12:00**

📌 **SCREEN:** VS Code — `orchestrator/agent.py`

---

**→ Open `orchestrator/agent.py`. Point at the `run()` method signature.**

> "Here's the orchestrator. `run()` is the pipeline entry point. Notice the `on_progress` callback parameter — this is how we stream real-time WebSocket events to the frontend without coupling the pipeline logic to HTTP. The orchestrator doesn't know it's behind a web server. It just fires the callback at each layer transition."

**→ Scroll to `_run_mcp_tools`. Point at `asyncio.gather` and the `_run_and_notify` wrapper.**

> "Tools run in parallel via `asyncio.gather`. I wrapped each call in `_run_and_notify` — results stream to the frontend as each tool finishes, not after all three complete. That's what makes the pipeline animation feel live."

**→ Open `subagents/base.py`. Scroll to `_build_system_prompt`.**

> "Every subagent gets this system prompt. Evidence is mandatory — no exceptions. If a finding doesn't cite tool output or a diff line verbatim, the review agent will suppress it. The architecture makes hallucination expensive."

**→ Open `review_agent/agent.py`. Scroll to `_DISPOSITION_SCHEMA`. Point at `tool_choice: tool`.**

> "The review agent uses forced tool use. It cannot produce prose outside the structured schema. The output is always a typed `ReviewDisposition` — verdict, ranked findings, suppressed count, summary. That's what hits the database and what the UI renders."

**→ Open `.claude/hooks/post_tool_use.py`. Scroll to `_post_to_api`.**

> "And this is the hook layer. When Claude Code writes any Python file, this fires automatically — generates a diff, checks if the web server is running, and POSTs the diff directly to the API. The pipeline reviews its own development changes. We'll see this live in a moment."

---

## ⏱ 12:00 — SECTION 3b: Implementation — Live Demo
**Target: 4:00 → end at 16:00**

📌 **SCREEN:** Browser → `http://localhost:8000` — Dashboard

---

> "Now let me show this running. FastAPI backend, React frontend, WebSocket for live progress."

**→ Point briefly at the Dashboard stat cards.**

> "Dashboard shows historical reviews, stats, time saved, and the latest eval regression score."

**→ Click 'New Review' in the sidebar.**

> "I'm going to submit a diff with deliberate vulnerabilities. Let me load the example."

**→ Click 'Load example'. Let the diff appear in the textarea. Scroll it briefly.**

> "Authentication module — hardcoded secret key, SQL injection via f-string, MD5 password hashing. Realistic-looking, obviously broken. Exactly the kind of thing that slips through a rushed manual review."

**→ Click 'Run Review'. Wait for redirect to the Review Detail page.**

> "Watch the pipeline. Layer 1 — skills loaded. Layer 2 — orchestrator routing the diff."

**→ Wait for Layer 3a to start. Point at the tool badges appearing.**

> "Layer 3a — ruff, mypy, bandit running in parallel. You can see each one completing as results stream in."

**→ Wait for Layer 3b. Point at the security, architecture, style badges.**

> "Layer 3b — three subagents simultaneously. The security agent already has bandit's output. It's grounding its analysis before forming any verdict."

**→ Wait for Layer 4 and the verdict banner.**

> "Layer 4 — review agent validating traceability. And there: Request Changes."

**→ Scroll down. Expand the first finding card (bandit B105 — hardcoded secret).**

> "Three findings, all traceable. This one — bandit B105, hardcoded password. The evidence field quotes the bandit output verbatim. Every finding is auditable back to a tool result."

**→ Expand the SQL injection finding.**

> "SQL injection, bandit B608, high severity. File, line, evidence, concrete suggestion. That's actionable AI review."

---

> ### ⚡ BREAKTHROUGH 1 — Live Hook Firing
> **⏱ ~16:00 · 75 seconds · THE moment that separates this from every other demo**

📌 **SCREEN:** VS Code — switch to `mcp_server/server.py`

---

> "Now watch what happens when I save a file through Claude Code."

**→ In VS Code, use Claude Code to make a trivial one-line change to `mcp_server/server.py` — e.g. add a comment. Let Claude write the file.**

**→ Watch the terminal where `python main.py ui` is running. Wait for the line:**
```
[AIWT] ✓ Live review started → http://localhost:8000/reviews/...
```

> "The `post_tool_use.py` hook fired automatically. It detected the server was running and POSTed the diff directly to the pipeline."

**→ Switch to browser → Dashboard. Refresh if needed. Point at the new review at the top with the `⚡ AUTO` badge.**

> "The pipeline is reviewing its own changes. I didn't click anything — Claude wrote a file, the hook intercepted it, and the system governed itself. That's the meta-layer: AI tooling that enforces quality gates on AI-written code."

**→ Click the AUTO review. Watch the pipeline animate for a few seconds.**

> "Same pipeline, same layers, same traceability rules — just triggered automatically."

---

> ### ⚡ BREAKTHROUGH 4 — OTel Traces
> **⏱ ~17:15 · 30 seconds**
> *(Skip this beat if observability stack is not running)*

📌 **SCREEN:** Review Detail page — still showing the completed or running demo review

---

**→ Click the "View OTel Traces →" button in the top-right of the review detail page.**

> "Every pipeline run emits OpenTelemetry spans. I can jump directly into the observability dashboard and see the full distributed trace — orchestrator, subagents, review agent — with timing and attributes on each span. Production-grade instrumentation, not a demo afterthought."

**→ Show the trace briefly, then navigate back to the AIWT tab.**

---

## ⏱ 17:45 — SECTION 4a: Testing — Golden Dataset
**Target: 1:15 → end at 19:00**

📌 **SCREEN:** VS Code — `eval/golden_dataset.json`

---

**→ Open `eval/golden_dataset.json`. Show one case — point at `expected.verdict`, `required_findings`, `forbidden_verdicts`.**

> "Testing a probabilistic system requires a principled approach. I built an LLM-as-judge eval harness — 15 hand-crafted golden cases covering clean diffs, security-only issues, architecture violations, partial code snippets.
>
> Each case defines the expected verdict, required findings that must appear, and forbidden verdicts. The judge scores on three dimensions: traceability, accuracy, and actionability."

**→ Switch to terminal. Run:**
```bash
python main.py eval --case GC-001 --verbose
```

> "Single case run to show the output format."

**→ Wait for result. Point at the three dimension scores.**

> "4.7 out of 5. Traceability, accuracy, actionability. Regression threshold is 4.0 — below that, the pipeline is degraded."

---

> ### ⚡ BREAKTHROUGH 2 — Eval Degradation
> **⏱ ~19:00 · 2:30 · Shows model lifecycle management in practice**

📌 **SCREEN:** VS Code — `skills/v1/security_review.md`

---

> "Now let me show what model lifecycle management actually looks like — not as a concept."

**→ Open `skills/v1/security_review.md`. Find a paragraph about hardcoded secrets or OWASP A02. Delete it. Save the file.**

> "I've just degraded the security skill — removed a key detection rule. Let me measure the impact."

**→ Switch to terminal. Run:**
```bash
python main.py eval --compare
```

> "The `--compare` flag shows deltas against the previous run."

**→ Wait for results. As they print, point at the red delta arrows and FAIL markers.**

> "There — specific cases regressed. The delta arrows show exactly where accuracy dropped. That's the eval catching a skill change before it ships. This is why you don't eyeball prompts — you measure them."

**→ In VS Code, undo the deletion with Ctrl+Z. Save. Run in terminal:**
```bash
python main.py eval --compare
```

> "Reverted the skill. Running again."

**→ Point at the green arrows in the output.**

> "Scores recover. Green arrows. This is the full model lifecycle loop: change a skill, measure, ship or revert. Every change is verifiable. No guessing, no vibes-based prompt engineering."

---

## ⏱ 21:30 — SECTION 5: Deployment
**Target: 1:30 → end at 23:00**

📌 **SCREEN:** Terminal

---

**→ Run in terminal:**
```bash
python main.py --help
```

> "The full toolkit is a single Python project. Four commands: `review` for CLI reviews, `eval` for the harness, `serve` to expose it as an MCP server for Claude Code integration, and `ui` to start the web server."

**→ Open `pyproject.toml`. Point at the `[project.optional-dependencies]` section.**

> "`pip install -e '.[ui]'` adds the web server. `pip install -e '.[dev]'` adds the deterministic tools. Clean separation of concerns at the dependency level too."

**→ Open browser to `http://localhost:8000/api/docs`.**

> "Auto-generated OpenAPI docs — every endpoint documented, request and response schemas validated by Pydantic. In production you'd containerise this, put it behind nginx, wire the OTel exporter to your stack. All the instrumentation is already there."

---

## ⏱ 23:00 — SECTION 6: AI/ML Deep Dive
**Target: 4:00 → end at 27:00**

📌 **SCREEN:** VS Code — `.claude/hooks/` directory visible in sidebar

---

**→ Open `.claude/hooks/pre_tool_use.py`.**

> "I want to show the development workflow, not just the product.
>
> This pre-commit hook intercepts every `git commit` command in this repo and runs the review pipeline on the staged diff. The tooling reviews its own commits. That's a governed development loop — the system enforces its own standards on itself."

**→ Open `skills/v1/security_review.md`.**

> "The skill files are the most important artefact in this project from an AI engineering perspective. Structured markdown encoding domain expertise — OWASP rules, SOLID principles, style constraints — in a format that's both human-readable and machine-consumable.
>
> When I want to update what the security agent knows, I edit this file and run the eval. Score holds above 4.0 — the change ships. That's model lifecycle: edit skill, evaluate, regress or ship. No model training, no fine-tuning. Just structured prompting with deterministic evaluation."

**→ Open `AGENTS.md`. Scroll slowly.**

> "`AGENTS.md` is the governance layer for the entire repository. Any agent operating here — Claude Code itself, the subagents, the review agent — reads this file at startup and operates within its constraints. Tool sequencing requirements. Mandatory evidence fields. Scope boundaries. It's a system prompt for the repository, not for a single conversation.
>
> The key insight: AI-first development isn't using Claude to write code faster. It's designing systems where AI reasoning is structurally constrained by verifiable evidence. That's the difference between reliable agentic AI and an impressive demo that fails in production."

---

## ⏱ 27:00 — Closing + Domain Pivot
**Target: 1:00 → end at 28:00**

📌 **SCREEN:** Browser → Dashboard — showing the reviews from the demo, including the AUTO hook review

---

**→ Point at the dashboard: stat cards, eval score, review list with the AUTO badge.**

> "To recap: five-layer governed pipeline, MCP server connecting Claude to real tooling, parallel subagents that must cite evidence, an independent review agent that validates traceability, an LLM-as-judge eval harness with a regression threshold, and OTel instrumentation on every run. The hook layer makes the whole thing self-governing — it reviews its own changes.
>
> Everything you've seen is domain-agnostic. For Innovorg specifically — where you're shipping content generation pipelines, skill taxonomy APIs, and certification logic — I'd extend the skill library with domain rules: validate AI-generated learning content against your taxonomy schema, flag certification boundary violations, enforce learning-path integrity constraints. Same pipeline, same eval harness, same OTel — different skills.
>
> That's the level of engineering rigour I bring to AI-automation work."

**→ Stop recording.**

---

## Key phrases — land these verbatim

| Phrase | Where |
|---|---|
| *"Grounded in deterministic tool output before any LLM judgement occurs"* | Section 1 / 2 |
| *"Enforced at the design level, not the prompt level"* | Section 1 |
| *"The sequencing constraint IS the product"* | Section 2 |
| *"The system governs itself"* | ⚡ Breakthrough 1 |
| *"15 hours of senior developer time back per week"* | ⚡ Time Saved |
| *"Change a skill, measure the impact, ship or revert"* | ⚡ Breakthrough 2 |
| *"No guessing, no vibes-based prompt engineering"* | ⚡ Breakthrough 2 |
| *"A system prompt for the repository, not for a single conversation"* | Section 6 |
| *"Reliable agentic AI vs an impressive demo that fails in production"* | Section 6 |
| *"Same pipeline, same eval harness — different skills"* | Closing |
