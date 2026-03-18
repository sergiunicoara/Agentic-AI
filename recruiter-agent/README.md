# 🚀 Sergiu – AI Recruiter Tour Agent
### Production-ready Multi-Agent System (Google/Kaggle Agents Style)

This project implements a production-grade AI Recruiter Tour Agent inspired by the Google/Kaggle "Agents" course. It acts as an interactive recruiter companion, helping hiring managers instantly understand your strongest qualifications through agentic workflows — with a full evaluation and observability stack.

---

## 🧠 Core Capabilities

* **✔️ Deterministic Multi-Stage Pipeline:** Role extraction → criteria parsing → project ranking → CV Q&A — no LLM in the orchestrator loop.
* **✔️ Recruiter-Aware Entry:** Tailors first messages based on referral source (GitHub/LinkedIn).
* **✔️ Project Relevance Ranking:** Gemini embeddings score and shortlist the most relevant portfolio projects per role.
* **✔️ Deep-Dive Flow:** Explains impact and role-match project-by-project with transparent reasoning.
* **✔️ ATS-Ready Outputs:** Generates polished ATS summaries and recruiter email drafts.
* **✔️ CV RAG (Gemini Embeddings):** High-precision retrieval over the candidate CV using `text-embedding-004`.
* **✔️ Full Trajectory Logging:** Every turn (user + agent) recorded with ISO timestamps and session ID, emitted to structured Cloud Logs.
* **✔️ LLM-as-a-Judge:** Multi-metric evaluation — faithfulness, relevancy, and factuality (0.0–1.0 each) + overall 1–5 score per turn.
* **✔️ Golden Evaluation Dataset:** 15 hand-curated cases covering all pipeline stages, run against live endpoints via the eval suite.
* **✔️ Critic Agent (A2A):** Autonomous critic agent that calls the judge via the MCP tool interface, issues PASS/FAIL verdicts, and tracks per-session quality metrics.
* **✔️ MCP Tool Registry:** Agent capabilities exposed as named JSON-schema tools via `/mcp/tools` and `/mcp/call` for Agent-to-Agent interoperability.
* **✔️ OpenTelemetry Tracing:** OTel spans on every `/chat`, `/mcp/call`, and `/a2a/validate` request, wired to Cloud Trace on startup.
* **✔️ Voice Interface:** Browser-native STT (mic input) and TTS (AI responses read aloud) via the Web Speech API — no extra API keys required.

---

## 🗺️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│   index.html — JS chat UI + Web Speech API (STT / TTS)      │
└──────────────────────────┬──────────────────────────────────┘
                           │ POST /chat
┌──────────────────────────▼──────────────────────────────────┐
│                      ORCHESTRATOR                            │
│   agent.py — deterministic pipeline, no LLM in loop         │
│                                                              │
│   Stage 1 → extract_role()       regex heuristics           │
│   Stage 2 → criteria parsing     normalize_criteria()       │
│   Stage 3 → project ranking      keyword scoring            │
│   Stage 4 → CV Q&A               routes to RAG              │
└──────┬───────────────────┬────────────────┬─────────────────┘
       │                   │                │
┌──────▼──────┐   ┌────────▼───────┐   ┌───▼─────────────────┐
│  cv_rag.py  │   │   tools.py     │   │ github_portfolio.py  │
│             │   │                │   │                      │
│  Gemini     │   │ Keyword score  │   │ GitHub API           │
│  embeddings │   │ over tags +    │   │ + TTL cache (6h)     │
│  text-004   │   │ summary        │   │ + static fallback    │
│             │   │                │   │                      │
│  Chunk CV   │   │ ATS summary    │   │ Markdown → project   │
│  Cosine sim │   │ Email draft    │   │ dict parser          │
│  Gemini gen │   │                │   │                      │
└─────────────┘   └────────────────┘   └──────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│                    EVALUATION LAYER                          │
│                                                              │
│   judge.py          faithfulness / relevancy / factuality    │
│                     0.0–1.0 each + overall score 1–5        │
│                                                              │
│   critic_agent.py   A2A call → judge via MCP tool interface  │
│                     PASS / FAIL + recommended_actions        │
│                     per-session aggregate metrics            │
│                                                              │
│   eval_runner.py    15 golden cases → /chat + /mcp/call     │
│                     pass_rate, avg_faithfulness, ...         │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     MCP / A2A LAYER                          │
│                                                              │
│   /mcp/tools      tool discovery (JSON schemas)             │
│   /mcp/call       tool dispatch                             │
│   /a2a/validate   critic agent endpoint                     │
│   /a2a/summary    session aggregate metrics                 │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    OBSERVABILITY                             │
│   OTel spans on every endpoint → Cloud Trace                │
│   Trajectory logs: session_id + timestamps → Cloud Logging  │
│   Critic logs: verdict + all 3 metric dimensions            │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    DEPLOYMENT                                │
│   Google Cloud Run  --min-instances 0  --cpu-throttling     │
│   GOOGLE_API_KEY injected from Secret Manager               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI, Uvicorn |
| **LLM** | Gemini 1.5 Flash (`google-genai`) |
| **Embeddings** | `models/text-embedding-004` |
| **Evaluation** | LLM-as-a-Judge + `ops/eval_data.json` (15 golden cases) |
| **Observability** | OpenTelemetry tracing + structured trajectory logs → Cloud Logging |
| **A2A / MCP** | Critic Agent + MCP tool registry (`/mcp/tools`, `/mcp/call`, `/a2a/validate`) |
| **Frontend** | Vanilla JS chat UI with voice (Web Speech API) |
| **Cloud** | Google Cloud Run — zero-cost optimized (`--min-instances 0`, `--cpu-throttling`) |

---

## 📁 Project Structure

```text
recruiter-agent/
├── README.md                     <-- You are here
├── deploy.ps1                    <-- Automated zero-cost GCP deployment
├── Dockerfile                    <-- Optimized Python-slim container
├── requirements.txt              <-- Python dependencies
├── main.py                       <-- Uvicorn entry point
│
├── ops/
│   └── eval_data.json            <-- 15 golden evaluation cases (golden dataset)
│
├── app/
│   ├── agent.py                  <-- Deterministic orchestrator (role → criteria → projects → ATS)
│   ├── critic_agent.py           <-- Autonomous critic agent (A2A validator, PASS/FAIL verdicts)
│   ├── cv_rag.py                 <-- CV vector search / RAG (Gemini embeddings)
│   ├── judge.py                  <-- LLM-as-a-Judge (faithfulness, relevancy, factuality)
│   ├── mcp.py                    <-- MCP-style tool registry + dispatcher
│   ├── tools.py                  <-- Project ranking + ATS generation
│   ├── github_portfolio.py       <-- Live GitHub portfolio loader (TTL-cached)
│   ├── server.py                 <-- FastAPI routes (/chat, /mcp/*, /a2a/*)
│   ├── quality.py                <-- Trajectory model (Step + timestamps + session ID)
│   ├── session_store.py          <-- Session state management
│   ├── otel.py                   <-- OpenTelemetry tracer factory
│   ├── memory/
│   │   ├── store.py              <-- Long-term memory store
│   │   └── extractor.py         <-- Memory extraction logic
│   ├── telemetry/
│   │   ├── tracing.py            <-- OTel TracerProvider setup (OTLP or Console)
│   │   ├── logging.py            <-- Structured logging configuration
│   │   └── metrics.py            <-- OTel metrics
│   └── ops/
│       └── eval_runner.py        <-- Eval suite (loads golden dataset, aggregates metrics)
│
└── frontend/
    └── index.html                <-- Chat UI with voice (STT + TTS)
```

---

## 🤖 Agent-to-Agent (A2A) Architecture

The system implements a two-agent architecture connected via an MCP-inspired tool registry:

```
Recruiter Agent (/chat)
        │
        │  structured turn (user_message + agent_reply)
        ▼
  /a2a/validate
        │
        ▼
  Critic Agent (critic_agent.py)
        │  calls judge via MCP tool interface
        ▼
  /mcp/call → judge_recruiter_turn
        │
        ▼
  LLM Judge (judge.py)
        │  returns faithfulness / relevancy / factuality
        ▼
  PASS / FAIL verdict + recommended_actions
```

**Endpoints:**

| Endpoint | Description |
|---|---|
| `POST /a2a/validate` | Submit a recruiter turn for critic agent validation |
| `GET  /a2a/summary/{session_id}` | Aggregate quality metrics for a critic session |
| `GET  /mcp/tools` | Discover available MCP tools and their JSON schemas |
| `POST /mcp/call` | Dispatch a named MCP tool call |

**Available MCP tools:**

| Tool | Description |
|---|---|
| `cv_rag_query` | Answer a natural language question from the CV via RAG |
| `best_projects_for_role` | Return ranked portfolio projects for a role + criteria |
| `ats_summary_and_email` | Generate ATS summary and recruiter outreach email |
| `judge_recruiter_turn` | Run the LLM judge and return multi-metric scores |

---

## 🧪 Evaluation Suite (LLM-as-a-Judge)

Behavioral evaluation runs against live endpoints using the golden dataset.

**Golden dataset** — `ops/eval_data.json` — 15 hand-curated cases:
- Role extraction (plain sentence, JD paste, startup context)
- Criteria parsing (canonical and unrecognized inputs)
- Project deep-dive and ATS summary triggers
- CV Q&A (contact, skills, education)
- Session commands (reset, help, full JD paste)

**Scoring metrics per case:**

| Metric | Range | What it measures |
|---|---|---|
| `score` | 1–5 | Overall reply quality |
| `faithfulness` | 0.0–1.0 | Grounded, no hallucination |
| `relevancy` | 0.0–1.0 | Directly addresses the user question |
| `factuality` | 0.0–1.0 | Specific claims (projects, skills) are accurate |

**Run the eval suite:**
```bash
python -m app.ops.eval_runner --base-url http://localhost:8080
```

Output includes per-case results and aggregate metrics: `pass_rate`, `avg_score`, `avg_faithfulness`, `avg_relevancy`, `avg_factuality`.

---

## 🎙️ Voice Interface

Browser-native voice — no extra API keys or backend changes required.

| Feature | How to use |
|---|---|
| **Speech-to-text** | Click the mic icon next to Send → speak → transcript fills the input |
| **Text-to-speech** | Click the speaker icon on any AI message bubble to replay it |
| **Auto-speak** | Toggle `🔇 Auto-speak` in the header → turns `🔊` → new AI replies are read aloud automatically |
| **Stop** | A red `■ Stop` button appears while speech is playing — click to cancel immediately |

> Requires Chrome or Edge. Mic buttons are hidden automatically in browsers without Web Speech API support (e.g. Firefox).

---

## 🔭 Observability

Every request is instrumented end-to-end:

- **OTel spans** on `/chat` (with `agent.turn` child span), `/mcp/call`, and `/a2a/validate` — sent to Cloud Trace via OTLP or logged to console
- **Trajectory logs** — each chat turn emits a structured JSON log with `session_id`, `turn_count`, user step, and agent step (role, criteria, memory events)
- **Critic logs** — each validation emits `verdict`, `score`, and all three metric dimensions

---

## 🚀 Deployment (Zero-Cost Optimized)

**Prerequisites:**
- Google Cloud SDK + Docker Desktop installed
- `GOOGLE_API_KEY` stored in Secret Manager ([Google AI Studio](https://aistudio.google.com/app/apikey))

**Deploy:**
```powershell
.\deploy.ps1
```

The script creates the Artifact Registry repository, builds the Docker image, and deploys to Cloud Run.

---

## 💰 Cost-Control Features

- `--min-instances 0` — no billing for idle time (scales to zero)
- `--cpu-throttling` — stops CPU billing immediately after each request
- `--set-secrets` — `GOOGLE_API_KEY` injected from Secret Manager at runtime
- Artifact Registry standard storage (keep under 500 MB for free tier)
