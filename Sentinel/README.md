# 🛡️ Sentinel — Hallucination-Free Security Review for Vibe-Coded Agents

> **Every finding Sentinel reports traces to deterministic tool evidence.  
> Hallucinated findings are automatically dropped by the Adjudicator.**

Kaggle AI Agents Intensive Capstone · Track: **Agents for Business**  
Built with Google ADK + Gemini 2.5 Flash on Vertex AI

---

## The Problem

Vibe coding ships agents at unprecedented speed — and ships them vulnerable: prompt injection surfaces, confused-deputy privilege leaks, secrets in logs, dependency CVEs, unsafe `eval()` of model output.

The obvious fix — point an LLM at the code and ask "is this secure?" — fails the moment it matters: **LLM reviewers hallucinate findings**, so teams can't trust the output, so they ignore it.

Sentinel solves this at the architecture level, not the prompt level.

---

## The Innovation: The Evidence Gate

Every finding produced by Sentinel's specialist auditors must reference at least one `evidence_id` from the deterministic evidence store (bandit, ruff, pip-audit). An **Adjudicator agent** deletes any finding that can't prove itself.

```
Finding with no evidence_ids → DROPPED
Finding with fake evidence_ids → DROPPED  
Finding with real evidence_ids → SURVIVES
```

This eliminates hallucinated security findings structurally — not by asking the model nicely, but by making it architecturally impossible to emit an unsupported finding.

**Note on the auditors:** the four deterministic specialists (Injection, Privilege, Supply Chain, RedTeam) are lookup tables over tool output — they never *can* hallucinate, so the gate is defense-in-depth for them. The **LLM Auditor** (`sentinel/agents/llm_auditor.py`, opt-in via `--llm-auditor` / `review_with_llm_auditor`) is different: it reads the raw source and reasons freely, which means it *can* propose a finding with a fabricated `evidence_id`. That's the auditor whose output the gate actually has to defend against. `tests/test_llm_auditor.py::test_llm_hallucinated_evidence_id_is_dropped_by_gate` proves the drop happens on a real (mocked) LLM response — `tests/test_adjudicator.py::test_finding_with_fake_evidence_id_is_dropped` proves the same logic in isolation.

---

## Results

| Metric | Value |
|---|---|
| Target detection rate | **100%** (5/5 vulnerable targets detected) |
| Hallucinated-finding rate on clean controls | **0%** |
| False positives on clean controls | **0** (C1 and C2 both pass with zero findings) |
| Tests passing | **60** |
| Course concepts demonstrated | **6 / 6** |

---

## Architecture

Seven-stage ADK pipeline:

```
SentinelOrchestrator (Gemini 2.5 Flash)
│
└─► Sequential Pipeline
    │
    ├─ 1. ScopeAgent          Profile target → select Skills
    ├─ 2. EvidenceAgent       Call MCP tools over real MCP transport (NO LLM)
    ├─ 3. Specialist Auditors
    │     ├─ InjectionAuditor   (loads prompt-injection-defense SKILL) — deterministic
    │     ├─ PrivilegeAuditor   (loads confused-deputy-iam SKILL) — deterministic
    │     ├─ SupplyChainAuditor (loads supply-chain-integrity SKILL) — deterministic
    │     ├─ RedTeamAuditor     (consumes trajectory evidence) — deterministic
    │     └─ LLMAuditor         (opt-in, Gemini) — the only auditor that CAN hallucinate
    ├─ 4. RedTeamRunner       Fire 8 adversarial payloads → trajectory evidence
    │     ├─ static  (sentinel/redteam/runner.py)       — textual surface match
    │     └─ live    (sentinel/redteam/live_runner.py)  — sandboxed real execution, opt-in
    ├─ 5. AdjudicatorAgent    ← THE TRUST GATE: drop findings without evidence
    ├─ 6. HITLGate            Pause before high-severity auto-remediation
    └─ 7. AttestationAgent    Risk-stratified verdict + immutable audit trail
```

**Live red team** (`--live-red-team`, opt-in, off by default) actually executes the corpus payloads against the target's real functions instead of only checking for static surfaces — e.g. it really calls `eval()` on an adversarial string and really fires a `subprocess` gadget, then reports what happened. Containment, not honor system:
- Every (function, payload) pair runs in its **own subprocess**, spawned by `sentinel/redteam/_live_worker.py` — target code is never imported in the main Sentinel process.
- The subprocess gets a **disposable temp directory as cwd** (file writes/deletes land there, then it's deleted), a **scrubbed environment** (no inherited credentials), **network sockets patched to raise** before the target module is even imported (covers DNS resolution and the connect step — verified against a real domain, not just a fake one), a **hard timeout**, and (POSIX) **CPU/memory rlimits**.
- Only functions whose first required parameter is free-form text (str/bytes) **and not named like a path** (`path`/`dir`/`file`/`filename`) are ever called with a raw payload — enforced inside the worker, so an adversarial string can never reach a filesystem-path parameter.
- Restricted to the same scan-root allow-list the MCP evidence server enforces — this is for the bundled, trusted target corpus, not arbitrary third-party code.
- See `sentinel/redteam/live_runner.py`'s module docstring for the full model, and `tests/test_live_redteam.py` for the containment proofs (no files leak into the real repo, path-like params are never called, traversal is blocked, network-blocked outcomes don't count as confirmed).

**MCP Evidence Server** (FastMCP, called over its real in-process MCP transport) wraps deterministic tools:
- `security_scan` — bandit (eval, subprocess, pickle, SQL injection, hardcoded secrets)
- `lint_scan` — ruff (style and error findings with line locators)
- `dependency_scan` — pip-audit (dependency CVEs)
- Every tool validates `target_path` against an allowed scan root and file-count/size limits before touching the filesystem — see `_validate_target` in `sentinel/mcp/evidence_server.py`.

**Agent Skills** — domain expertise as composable `SKILL.md` modules:
- `prompt-injection-defense` — injection surfaces, eval, subprocess
- `confused-deputy-iam` — credential forwarding, hardcoded secrets
- `supply-chain-integrity` — dependency vulnerabilities

**A2A** — Sentinel publishes an agent card at `/.well-known/agent-card.json` and exposes a task-based HTTP API for remote agent-to-agent review requests. Bearer-token auth is opt-in (`SENTINEL_A2A_TOKEN`); completed tasks are purged after `SENTINEL_TASK_TTL_SECONDS` (default 1h).

**CI integration** — `python -m sentinel.pipeline <target> --sarif report.sarif.json --fail-on fail` runs headless and exits non-zero on a failing verdict, for wiring into a CI security gate.

---

## Course Concepts Demonstrated

| Concept | Status | Where |
|---|---|---|
| Multi-agent system (ADK) | ✅ | `sentinel/agents/`, `sentinel/orchestrator/` |
| MCP Server | ✅ | `sentinel/mcp/evidence_server.py` |
| Agent Skills | ✅ | `sentinel/skills/` |
| Security features | ✅ | `sentinel/agents/adjudicator.py`, `sentinel/redteam/` |
| Deployability | ✅ | `deploy/Dockerfile`, Cloud Run |
| Antigravity | ✅ | Built spec-driven in Antigravity |

**Bonus (last cohort only roadmapped these):** A2A agent card + HTTP endpoint, HITL gate, trajectory evaluation, spec-driven development.

---

## Eval Corpus

| Target | Seeded Vulnerability | Detected | Verdict |
|---|---|---|---|
| T1 | eval() + subprocess shell=True | ✅ | FAIL |
| T2 | Hardcoded API key/password | ✅ | FAIL |
| T3 | Hardcoded secrets/credentials | ✅ | FAIL |
| T4 | SQL injection via string concat | ✅ | FAIL |
| T5 | pickle deserialization + subprocess | ✅ | FAIL |
| C1 | None (clean control) | ✅ | PASS |
| C2 | None (clean control) | ✅ | PASS |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Google Cloud account with Vertex AI enabled
- `gcloud` CLI installed

### Setup

```bash
git clone https://github.com/sergiunicoara/Agentic-AI
cd Agentic-AI/Sentinel
python -m venv venv

# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

uv pip install -r requirements.txt
```

### Authenticate (no API key needed)

```bash
gcloud auth application-default login
```

### Environment

Create `.env` in the `Sentinel/` folder:

```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=global
```

### Run the agent

```bash
adk run sentinel/orchestrator
```

Then ask:
```
Review the target at targets/t1_injection
Review the target at targets/t1_injection with red team enabled
Review the target at targets/t1_injection with live red team execution
Review the target at targets/t1_injection with the LLM auditor enabled
Request remediation approval for targets/t1_injection
Show me your agent capabilities
```

### Run the eval corpus

```bash
python -m sentinel.eval.runner
```

### Run tests

```bash
pytest tests/ -v
```

### Run from the CLI (CI-friendly)

```bash
python -m sentinel.pipeline targets/t1_injection
python -m sentinel.pipeline targets/t1_injection --red-team --sarif report.sarif.json
python -m sentinel.pipeline targets/t1_injection --live-red-team   # sandboxed real execution
python -m sentinel.pipeline targets/t1_injection --llm-auditor   # requires Vertex AI credentials
```

Exits non-zero when the verdict meets `--fail-on` (default `fail`) — wire this into a CI security gate.

### Start the A2A server

```bash
python -m sentinel.a2a.server
```

Agent card available at: `http://localhost:8080/.well-known/agent-card.json`

Set `SENTINEL_A2A_TOKEN` to require `Authorization: Bearer <token>` on review endpoints (unset by default for local demo use).

---

## Project Structure

```
Sentinel/
├── sentinel/
│   ├── orchestrator/       # ADK root agent + 6 tools
│   ├── agents/             # EvidenceAgent, 5 auditors, Adjudicator, HITL gate
│   ├── mcp/                # FastMCP evidence server (bandit, ruff, pip-audit) + path/size guard
│   ├── models/             # Pydantic schemas (Evidence, Finding, Attestation, pillar taxonomy)
│   ├── skills/             # 3 SKILL.md domain expertise modules
│   ├── redteam/            # 8-payload corpus + static runner + sandboxed live runner
│   ├── a2a/                # Agent card, A2A server (optional auth + TTL eviction), A2A client
│   └── eval/               # Eval runner + metrics + SARIF export
├── targets/                # Planted-bug corpus (T1, T2, T3, T4, T5, C1, C2)
├── tests/                  # 60 tests across all components
├── deploy/                 # Dockerfile + Cloud Run deploy script
├── hello_agent/            # ADK hello-world (setup verification)
├── requirements.txt
├── pyproject.toml
└── .env                    # Not committed — see Environment section above
```

---

## Deploy to Cloud Run

Run from the `Sentinel/` repo root (the script resolves the build context itself):

```bash
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

Or manually — note `-f deploy/Dockerfile` with the **repo root** as the build context, so `requirements.txt` and the `sentinel/` package are included (and `.dockerignore` keeps `.env` out of the image):

```bash
docker build -f deploy/Dockerfile -t gcr.io/recruiter-sergiu-260213/sentinel:latest .
docker push gcr.io/recruiter-sergiu-260213/sentinel:latest
gcloud run deploy sentinel \
  --image gcr.io/recruiter-sergiu-260213/sentinel:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

> For anything beyond a demo, set `SENTINEL_A2A_TOKEN` on the service and drop `--allow-unauthenticated`, or the review endpoints are open to the internet.

---

## The Self-Review Demo

Sentinel can review its own code:

```
adk run sentinel/orchestrator
> Review the target at sentinel/mcp
```

This is the defining moment: the harness reviewing itself, finding real issues in its own code, with every finding backed by deterministic evidence.
Sentinel flagged a real issue in its own MCP evidence server — subprocess 
usage without input validation (bandit B603, evidence ev_bandit_9dc5388a) — 
and returned PASS_WITH_FINDINGS. The finding is backed by deterministic 
evidence. No hallucination. The harness reviewing itself and finding a 
genuine issue is the system working exactly as designed.
---

## Security Note

No API keys are stored in this repository. Authentication uses Google Cloud Application Default Credentials (`gcloud auth application-default login`). Never commit `.env` files or credential files.

---

## Author

**Sergiu Nicoară** — AI Engineer  
GitHub: [sergiunicoara](https://github.com/sergiunicoara)  
LinkedIn: [sergiu-nicoara-31b27013](https://www.linkedin.com/in/sergiu-nicoara-31b27013/)
