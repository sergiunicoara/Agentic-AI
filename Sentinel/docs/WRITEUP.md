<!--
Kaggle Writeup draft for Sentinel — AI Agents Intensive Vibe Coding Capstone.
Paste the Title/Subtitle and body below into the Kaggle Writeup editor.
Word count (body, excluding this comment and headers used purely as
navigation) is noted at the bottom — keep it under 2,500 per the rules.
-->

# TITLE
Sentinel: Hallucination-Free Security Review for Vibe-Coded Agents

# SUBTITLE
A multi-agent system that reviews AI agents for security flaws — where every finding must prove itself with deterministic evidence, or the system deletes it itself.

---

## The Problem

Vibe coding lets anyone ship an AI agent in an afternoon. It also lets anyone ship one with `eval()` on user input, a hardcoded API key, or a tool that fetches whatever URL it's handed. These aren't exotic bugs — they're the default outcome of moving fast without a security review step, because nobody pairs "build an agent quickly" with "review the agent's security."

The obvious fix is to point an LLM at the code and ask "is this secure?" That fails the moment it matters: LLM reviewers hallucinate findings. They invent a vulnerability that isn't there, or cite a line number that doesn't exist, with the same confident tone as a real finding. A security team that gets burned by one fabricated finding stops trusting the tool — and once they stop trusting it, they stop reading its output at all. The cost of an unreliable security scanner isn't bad findings; it's that *good* findings get ignored along with the bad ones.

Sentinel's bet is that this is a business problem with cost on both sides: the cost of shipping a real vulnerability, and the cost of alert fatigue from a scanner nobody trusts. Both sides are why a security team would actually adopt one tool over another — not raw detection count, but whether they can act on every single thing it tells them.

## The Solution: Make Unsupported Findings Structurally Impossible to Keep

Sentinel solves this at the architecture level, not the prompt level. Every finding a specialist auditor proposes must cite at least one `evidence_id` from a deterministic evidence store — built by running real static-analysis tools (bandit, ruff, pip-audit, semgrep) against the target's code, never by asking an LLM "did you find anything." An **Adjudicator** then checks every proposed finding against that store:

```
Finding with no evidence_id        → DROPPED
Finding with a fabricated evidence_id → DROPPED
Finding with a real evidence_id    → SURVIVES
```

This isn't a guideline a model can drift away from. It's a Pydantic schema validator (`Finding.evidence_ids` cannot be empty) plus a set-membership check (the cited ID must exist in the evidence store collected for *this specific scan*). A model can write whatever it wants; only what it can prove survives.

**The deliberate design choice — putting the LLM on a leash.** Four of Sentinel's five specialist auditors (Injection, Privilege, SupplyChain, RedTeam) are deterministic lookup tables over tool output — they map a bandit test ID or a semgrep rule ID to a finding template. They *cannot* hallucinate; there's no LLM in that path at all. The one auditor that reasons freely — the LLM Auditor, opt-in, reads raw source and proposes findings in natural language — is exactly the one whose output the Adjudicator has to defend against. I measured this live, not just claimed it: across the eval corpus, the LLM auditor proposed 18 candidate findings; 15 survived; 3 were dropped. None of the drops were fabricated evidence IDs — each cited real evidence but wrote `severity: "medium"` instead of the schema's required literal `"med"`. That's arguably a *better* proof than a clean hallucination catch: it shows the gate enforces the whole Finding contract, not one field, and that even a well-instructed model drifts on exact-string requirements often enough that structural validation — not prompting — is what should be trusted.

**Detection ceiling, raised on purpose.** A reasonable critique of any scanner built on bandit is "you're just bandit with a UI." Sentinel answers this directly: I wrote two project-specific semgrep rules — one for SSRF via an unvalidated URL (a data-flow pattern bandit has no rule for at all), one matching known LLM/cloud API key *formats* (`sk-...`, `AIza...`) regardless of variable name (bandit's hardcoded-password heuristic matches on names like `password`/`token`/`secret` — notably not `key`). I then built a target, `t6_ssrf`, specifically containing both gaps, and a test (`test_bandit_finds_nothing_relevant_on_t6`) that asserts bandit catches *neither*. Sentinel's full pipeline catches both, end-to-end, via semgrep evidence alone. The detection ceiling moved, and it's proven by a test, not asserted in a README.

## Architecture

A multi-agent ADK system: three real ADK agents sit at the boundaries, plus one opt-in Gemini-backed auditor that is deliberately *not* an ADK agent, and every load-bearing step in between is deterministic Python:

- **SentinelOrchestrator** (ADK Agent, Gemini 2.5 Flash) — the agent the user or an A2A peer talks to. Routes intent across 8 tools: five end-to-end review modes (standard, +red-team, +live red-team, +LLM auditor, +HITL remediation) plus per-stage tools and capability discovery.
- **ScopeAgent** (ADK Agent) — wraps `profile_target()`, profiling a target's code and selecting which security Skills apply, and explaining why.
- **AttestationAgent** (ADK Agent) — wraps `produce_attestation()`, which runs the Adjudicator and returns the signed, risk-stratified verdict. It can *explain* the gate's decision; it cannot override it.
- **LLM Auditor** (Gemini-backed, opt-in, *not* an ADK agent — a direct `google.genai` API call used as a one-shot batch classifier) — the one auditor that reasons freely about source code, discussed above.

Between Scope and Attestation, the pipeline is plain functions: an **Evidence Agent** calls four tools through a real in-process MCP server (`security_scan`/bandit, `lint_scan`/ruff, `dependency_scan`/pip-audit, `semgrep_scan`); four deterministic **Auditors** map evidence to candidate findings; a **Red Team** stage fires 8 adversarial payloads, either as a static textual-surface check or — opt-in — by *actually executing* them against the target's real functions inside a sandboxed subprocess (disposable temp directory, scrubbed environment, network sockets patched to fail closed, hard timeout, POSIX resource limits, and a hard rule that adversarial strings are never passed into a parameter that looks like a filesystem path); and the **Adjudicator** is the gate described above. A **HITL Gate** pauses before any high-severity auto-remediation for human approval. Output is a signed `Attestation` — exportable as a SARIF 2.1.0 report for CI gate integration, and streamed live to a React/WebSocket dashboard that shows each gate decision (SURVIVED / DROPPED) as it happens.

(Architecture diagram: `docs/architecture.svg` in the repo, embedded in the README.)

## Course Concepts Demonstrated — 5 (3 required minimum)

- **Multi-agent system (ADK):** three real ADK agents — Orchestrator, Scope, Attestation — with Scope and Attestation wired as orchestrator tools and covered by tests that assert they're actually invoked, not just defined. (The LLM Auditor is a fourth model-backed specialist but a direct Gemini API call, not an ADK agent — kept distinct deliberately, see above.)
- **MCP Server:** `sentinel/mcp/evidence_server.py`, four tools, called over FastMCP's real in-process transport (not bypassed via direct function calls).
- **Agent Skills:** three composable `SKILL.md` modules (prompt-injection-defense, confused-deputy-iam, supply-chain-integrity) loaded progressively — front-matter first to decide relevance, full content only when a skill activates for a given scan.
- **Security features:** the project's entire premise — the evidence gate, plus a genuinely sandboxed live red-team execution mode, are themselves the security feature, not an add-on.
- **Deployability:** multi-stage `deploy/Dockerfile` (Node builds React dashboard → Python runtime) + `deploy/deploy.sh` → Cloud Run, shown in the demo video. A live WebSocket dashboard (`sentinel/dashboard/`, React/Vite) is served from the same container at `/ui` — streaming every pipeline stage and gate decision (SURVIVED / DROPPED) in real time.
- *(Bonus, beyond the five above:* A2A agent-card + HTTP API with optional bearer auth and task-TTL eviction, SARIF/CI-gate export.)*

## Results

| Metric | Value |
|---|---|
| Target detection rate | 100% (6/6 vulnerable targets, including one bandit structurally cannot catch) |
| LLM-auditor evidence survival rate (measured live) | 83% (15/18 candidates; the 3 dropped were schema violations, not hallucinated evidence) |
| Hallucinated-finding rate on clean controls | 0% |
| False positives on clean controls | 0 |
| Tests passing | 75 |

The numbers that matter most aren't the 100% — a small bundled corpus making that easy is expected — but the 0% false-positive rate on clean controls and the *measured* (not assumed) 83% survival rate on the one auditor that can fail. Those are the numbers a security team adopting this tool would actually care about: does it cry wolf, and when it's wrong, does something catch it.

## Why This Matters for "Agents for Business"

The buyer is an engineering or security lead who already runs bandit/semgrep in CI and is tired of triaging false positives, or who wants an LLM-assisted review but can't get sign-off because "the LLM might just make things up" is a real, reasonable objection from their security team. Sentinel's pitch to that buyer isn't "more detections" — it's "you can wire this into a CI gate (`--fail-on fail`, SARIF output) and trust every line it produces, because the architecture won't let it lie to you." That's the adoptable feature: not detection count, but zero-tolerance for unverifiable claims, in a workflow (`docker build` → Cloud Run, or a GitHub Action) a team already has.

## The Build

Built iteratively over several "days" of work (see commit history: MCP evidence server → Skills + Adjudicator → full pipeline → red team + auditors → A2A + HITL → eval corpus → deployment hardening → live red-team sandboxing + semgrep + live gate measurement). Each stage added a course concept and a test suite; nothing shipped without `pytest` passing. Along the way, real bugs surfaced and got fixed rather than worked around: a genuine PyPI dependency conflict between `semgrep` and `fastmcp` (resolved by pinning the one `fastmcp` version whose `mcp` range still includes semgrep's exact pin); a Docker build-context mismatch that would have broken deployment and, if fixed naively, leaked `.env` into the image (fixed with a `.dockerignore` written *before* the context fix landed); an async FastAPI background task that called blocking scans synchronously, stalling the event loop; and a `semgrep` failure mode where one unreachable registry pack silently zeroed out the project's own offline-capable rules.

No API keys or secrets are in this repository. Authentication uses Google Cloud Application Default Credentials; `.env` is gitignored and the Docker build explicitly excludes it.

---

*(Word count of body above: ~1,530 — under the 2,500 limit, leaving room for screenshots/output excerpts inline if the Kaggle editor format benefits from them.)*
