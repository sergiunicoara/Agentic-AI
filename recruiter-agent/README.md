# 🚀 Sergiu – AI Recruiter Tour Agent
### Production-ready AI Agent (Google/Kaggle Agents Style)

This project implements a production-grade AI Recruiter Tour Agent inspired by the Google/Kaggle "Agents" course. It acts as an interactive recruiter companion, helping hiring managers instantly understand your strongest qualifications through agentic workflows.

---

## 🧠 Core Capabilities

* **✔️ Recruiter-Aware Entry:** Tailors first messages based on referral source (GitHub/LinkedIn).
* **✔️ Role & Criteria Extraction:** Deterministic heuristic pipeline — role extraction → criteria parsing → project ranking → CV Q&A.
* **✔️ Project Relevance Ranking:** Uses Gemini embeddings to compute a shortlist of the most relevant projects.
* **✔️ Deep-Dive Flow:** Explains impact and role-match project-by-project with transparent reasoning.
* **✔️ ATS-Ready Outputs:** Generates polished summaries and recruiter email drafts.
* **✔️ CV RAG (Gemini Embeddings):** High-precision retrieval using `text-embedding-004`.
* **✔️ Full Trajectory Logging:** Every turn (user + agent) is recorded with ISO timestamps and session ID, emitted to structured Cloud Logs.
* **✔️ LLM-as-a-Judge:** Multi-metric evaluation — faithfulness, relevancy, and factuality (0.0–1.0 each) + overall 1–5 score.
* **✔️ MCP Tool Registry (A2A):** Exposes agent capabilities as named JSON-schema tools via `/mcp/tools` and `/mcp/call` for programmatic evaluation and external integration.
* **✔️ Voice Interface:** Browser-native speech-to-text (mic input) and text-to-speech (AI responses read aloud) via the Web Speech API — no extra API keys required.

---

## 🏗️ Tech Stack

* **Backend:** FastAPI, Uvicorn
* **LLM:** Gemini 1.5 Flash (`google-genai`)
* **Embeddings:** `models/text-embedding-004`
* **Evaluation:** LLM-as-a-Judge (Gemini) with golden dataset (`ops/eval_data.json`)
* **Observability:** OpenTelemetry tracing + structured trajectory logs (Cloud Logging)
* **A2A Interface:** MCP-inspired tool registry (`/mcp/tools`, `/mcp/call`)
* **Frontend:** Lightweight JS chat UI with voice (Web Speech API)
* **Cloud:** Google Cloud Run (Containerized, zero-cost optimized)

---

## 📁 Project Structure

```text
recruiter-agent/
├── README.md                   <-- You are here
├── deploy.ps1                  <-- Automated Zero-Cost GCP Deployment
├── Dockerfile                  <-- Optimized Python-slim container
├── requirements.txt            <-- Dependencies
├── main.py                     <-- Entry point
├── ops/
│   └── eval_data.json          <-- 15 golden evaluation cases
├── app/
│   ├── agent.py                <-- Deterministic orchestrator (role → criteria → projects → ATS)
│   ├── cv_rag.py               <-- CV vector search / RAG (Gemini embeddings)
│   ├── judge.py                <-- LLM-as-a-Judge (faithfulness, relevancy, factuality)
│   ├── mcp.py                  <-- MCP-style tool registry (A2A interface)
│   ├── tools.py                <-- Project ranking + ATS generation
│   ├── github_portfolio.py     <-- Live GitHub portfolio loader (TTL-cached)
│   ├── server.py               <-- FastAPI routes (/chat, /mcp/tools, /mcp/call)
│   ├── quality.py              <-- Trajectory model (Step + Trajectory with timestamps)
│   ├── session_store.py        <-- Session state management
│   ├── otel.py                 <-- OpenTelemetry setup
│   ├── memory/                 <-- Session memory (store + extractor)
│   ├── telemetry/              <-- Tracing, metrics, structured logging
│   └── ops/
│       └── eval_runner.py      <-- Eval suite runner (loads golden dataset, aggregates metrics)
└── frontend/
    └── index.html              <-- Chat UI with voice (STT + TTS)
```

---

## 🎙️ Voice Interface

The chat UI includes browser-native voice support — no extra API keys or backend changes required.

| Feature | How to use |
|---|---|
| **Speech-to-text** | Click the mic icon next to the Send button → speak → transcript fills the input |
| **Text-to-speech** | Click the small speaker icon on any AI message bubble to replay it |
| **Auto-speak** | Toggle `🔇 Auto-speak` in the chat header → turns `🔊` → every new AI response is read aloud automatically |
| **Stop** | A red `■ Stop` button appears in the header while speech is playing; click to cancel immediately |

> Requires Chrome or Edge. Mic buttons are hidden automatically in browsers that don't support the Web Speech API (e.g. Firefox).

---

## 🧪 Evaluation Suite (LLM-as-a-Judge)

The agent includes a behavioral evaluation suite that runs against the live endpoints.

**Golden dataset:** `ops/eval_data.json` — 15 hand-curated cases covering:
- Role extraction (plain sentence, JD paste, startup context)
- Criteria parsing (canonical and unrecognized)
- Project deep-dive and ATS summary triggers
- CV Q&A (contact, skills, education)
- Session commands (reset, help)

**Scoring metrics per case (via `judge.py`):**

| Metric | Range | What it measures |
|---|---|---|
| `score` | 1–5 | Overall reply quality |
| `faithfulness` | 0.0–1.0 | Grounded, no hallucination |
| `relevancy` | 0.0–1.0 | Directly addresses the question |
| `factuality` | 0.0–1.0 | Specific claims are accurate |

**Run the eval suite:**
```bash
python -m app.ops.eval_runner --base-url http://localhost:8080
```

Results include per-case scores and aggregate metrics (pass rate, avg faithfulness, avg relevancy, avg factuality).

---

## 🔌 MCP Tool Registry (A2A Interface)

The agent exposes its capabilities as named JSON-schema tools via an MCP-inspired HTTP interface, enabling structured Agent-to-Agent (A2A) calls.

**Discover available tools:**
```
GET /mcp/tools
```

**Call a tool:**
```
POST /mcp/call
{ "tool": "judge_recruiter_turn", "arguments": { ... } }
```

| Tool | Description |
|---|---|
| `cv_rag_query` | Ask a natural language question answered from the CV via RAG |
| `best_projects_for_role` | Return ranked portfolio projects for a role + criteria |
| `ats_summary_and_email` | Generate ATS summary and recruiter outreach email |
| `judge_recruiter_turn` | Run the LLM judge over a recruiter-agent turn |

The eval runner uses `/mcp/call` to invoke the judge externally, making it a genuine A2A interaction.

---

## 🚀 Deployment (Zero-Cost Optimized)

This project is configured to run on the Google Cloud Free Tier. The included `deploy.ps1` script ensures the service scales to zero when not in use.

**Prerequisites:**
- Google Cloud SDK and Docker Desktop installed
- `GOOGLE_API_KEY` from [Google AI Studio](https://aistudio.google.com/app/apikey) stored in Secret Manager

**Deploy:**
```powershell
.\deploy.ps1
```

The script automatically creates the Artifact Registry repository, builds the Docker image, and deploys to Cloud Run with zero-cost settings.

---

## 💰 Cost-Control Features

- `--min-instances 0` — no billing for idle time
- `--cpu-throttling` — stops CPU billing immediately after request completion
- Artifact Registry standard storage (keep under 500 MB for free tier)
