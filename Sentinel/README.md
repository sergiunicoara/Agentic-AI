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

---

## Results

| Metric | Value |
|---|---|
| Detection recall | **100%** (4/4 vulnerable targets detected) |
| Hallucinated-finding rate on clean controls | **0%** |
| False positives on clean controls | **0** (C1 and C2 both pass with zero findings) |
| Tests passing | **34** |
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
    ├─ 2. EvidenceAgent       Run MCP tools → build evidence store (NO LLM)
    ├─ 3. Parallel Specialists
    │     ├─ InjectionAuditor   (loads prompt-injection-defense SKILL)
    │     ├─ PrivilegeAuditor   (loads confused-deputy-iam SKILL)
    │     └─ SupplyChainAuditor (loads supply-chain-integrity SKILL)
    ├─ 4. RedTeamAgent        Fire 8 adversarial payloads → trajectory evidence
    ├─ 5. AdjudicatorAgent    ← THE TRUST GATE: drop findings without evidence
    ├─ 6. HITLGate            Pause before high-severity auto-remediation
    └─ 7. AttestationAgent    Risk-stratified verdict + immutable audit trail
```

**MCP Evidence Server** (FastMCP) wraps deterministic tools:
- `security_scan` — bandit (eval, subprocess, pickle, SQL injection, hardcoded secrets)
- `lint_scan` — ruff (style and error findings with line locators)
- `dependency_scan` — pip-audit (dependency CVEs)

**Agent Skills** — domain expertise as composable `SKILL.md` modules:
- `prompt-injection-defense` — injection surfaces, eval, subprocess
- `confused-deputy-iam` — credential forwarding, hardcoded secrets
- `supply-chain-integrity` — dependency vulnerabilities

**A2A** — Sentinel publishes an agent card at `/.well-known/agent-card.json` and exposes a task-based HTTP API for remote agent-to-agent review requests.

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

pip install -r requirements.txt
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

### Start the A2A server

```bash
python -m sentinel.a2a.server
```

Agent card available at: `http://localhost:8080/.well-known/agent-card.json`

---

## Project Structure

```
Sentinel/
├── sentinel/
│   ├── orchestrator/       # ADK root agent + 4 tools
│   ├── agents/             # EvidenceAgent, auditors, Adjudicator, HITL gate
│   ├── mcp/                # FastMCP evidence server (bandit, ruff, pip-audit)
│   ├── models/             # Pydantic schemas (Evidence, Finding, Attestation)
│   ├── skills/             # 3 SKILL.md domain expertise modules
│   ├── redteam/            # 8-payload injection corpus + runner
│   ├── a2a/                # Agent card, A2A server, A2A client
│   └── eval/               # Eval runner + metrics
├── targets/                # Planted-bug corpus (T1, T3, T4, T5, C1, C2)
├── tests/                  # 34 tests across all components
├── deploy/                 # Dockerfile + Cloud Run deploy script
├── hello_agent/            # ADK hello-world (setup verification)
├── requirements.txt
├── pyproject.toml
└── .env                    # Not committed — see Environment section above
```

---

## Deploy to Cloud Run

```bash
cd deploy
chmod +x deploy.sh
./deploy.sh
```

Or manually:

```bash
docker build -t gcr.io/YOUR_PROJECT/sentinel:latest .
docker push gcr.io/YOUR_PROJECT/sentinel:latest
gcloud run deploy sentinel \
  --image gcr.io/YOUR_PROJECT/sentinel:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

---

## The Self-Review Demo

Sentinel can review its own code:

```
adk run sentinel/orchestrator
> Review the target at sentinel/agents
```

This is the defining moment: the harness reviewing itself, finding real issues in its own code, with every finding backed by deterministic evidence.

---

## Security Note

No API keys are stored in this repository. Authentication uses Google Cloud Application Default Credentials (`gcloud auth application-default login`). Never commit `.env` files or credential files.

---

## Author

**Sergiu Nicoară** — AI Engineer  
GitHub: [sergiunicoara](https://github.com/sergiunicoara)  
LinkedIn: [sergiu-nicoara-31b27013](https://www.linkedin.com/in/sergiu-nicoara-31b27013/)
