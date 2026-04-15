# Sergiu – AI Recruiter Tour Agent
### Production Voice AI + Multi-Agent System

An interactive AI recruiter agent that helps hiring managers understand Sergiu's strongest qualifications through agentic workflows — with a live voice pipeline, full evaluation stack, and observability.

**Live:** https://recruiter-agent-969006882005.europe-west1.run.app

---

## Core Capabilities

- **Deterministic orchestrator** — role extraction → criteria parsing → project ranking → CV Q&A with no LLM in the routing loop (35ms agent turn)
- **Real-time voice pipeline** — Deepgram nova-2 STT over WebSocket → agent → Google Neural2-D TTS with sentence-level streaming. Barge-in via RMS VAD. ~600ms speech-to-first-audio E2E.
- **Continuous conversation** — one mic press opens a persistent session; Deepgram auto-detects utterance end, agent responds, TTS streams back. No push-to-talk.
- **CV RAG** — Gemini `text-embedding-004` embeddings over the candidate CV for recruiter Q&A (phone, certifications, location, skills)
- **ATS outputs** — role-matched project deep dives, ATS-style summaries, recruiter email drafts
- **LLM-as-Judge** — multi-metric eval per turn: faithfulness, relevancy, factuality (0.0–1.0 each)
- **Critic Agent (A2A)** — autonomous critic calls the judge via MCP tool interface, issues PASS/FAIL verdicts, tracks session-level quality
- **MCP tool registry** — agent capabilities exposed as named JSON-schema tools via `/mcp/tools` + `/mcp/call`
- **OTel tracing** — every `/chat`, `/voice`, `/mcp/call`, `/a2a/validate` request has a span wired to Cloud Trace

---

## Architecture

```
Browser (index.html)
│
├── POST /chat ─────────────────────────────────────────────────────┐
│                                                                    │
└── WebSocket /voice                                                 │
      ├── send: PCM16 audio chunks (48kHz)                          │
      ├── send: JSON { barge_in / stop_session }                    │
      ├── recv: JSON { ready / transcript / reply / audio_end }     │
      └── recv: binary MP3 chunks                                   │
                                                                    │
┌───────────────────────────────────────────────────────────────────▼──┐
│                          FastAPI  (server.py)                         │
└──────────────┬────────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│                     voice_handler  (voice.py)                        │
│                                                                      │
│  Deepgram nova-2 WebSocket                                          │
│    PCM16 in → is_final transcripts → asyncio.Queue                  │
│                                                                      │
│  process() loop                                                      │
│    transcript → agent_turn() → reply                                │
│                                                                      │
│  Google Neural2-D TTS                                               │
│    reply → split sentences → parallel synthesis → MP3 stream        │
│                                                                      │
│  Barge-in: RMS VAD on mic → tts_cancel Event → abort mid-stream    │
│  Keepalive: zeros sent to Deepgram during TTS to hold connection    │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│                       agent_turn  (agent.py)                         │
│                                                                      │
│  Stage 1: extract_role()        regex, deterministic                │
│  Stage 2: criteria parsing      normalize_criteria()                │
│           voice_ai / production_rag / observability /               │
│           low_latency / leadership / ownership / communication      │
│  Stage 3: project ranking       keyword scoring over tags+summary   │
│  Stage 4: CV Q&A                routes to cv_rag.py                 │
└──────┬───────────────────┬─────────────────────────────────────────┘
       │                   │
┌──────▼──────┐   ┌────────▼──────────────────────────┐
│  cv_rag.py  │   │            tools.py                │
│             │   │                                    │
│  Gemini     │   │  STATIC_PROJECTS (priority):       │
│  embeddings │   │  • Production Voice AI Pipeline    │
│  text-004   │   │  • Agent Observability Dashboard   │
│             │   │  • GraphRAG + RAGAS Pipeline       │
│  Chunk CV   │   │                                    │
│  Cosine sim │   │  GitHub-backed (TTL 6h):           │
│  Gemini gen │   │  github_portfolio.py               │
└─────────────┘   │  → README.md files, depth ≤ 1     │
                  │  → system files filtered out        │
                  │                                    │
                  │  ATS summary + email draft         │
                  └────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       EVALUATION LAYER                               │
│                                                                      │
│  judge.py          faithfulness / relevancy / factuality 0.0–1.0   │
│  critic_agent.py   A2A → judge via MCP, PASS/FAIL + session agg.   │
│  eval_runner.py    15 golden cases → /chat + /mcp/call              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                         MCP / A2A LAYER                              │
│  /mcp/tools        tool discovery (JSON schemas)                    │
│  /mcp/call         tool dispatch                                    │
│  /a2a/validate     critic agent endpoint                            │
│  /a2a/summary      session aggregate metrics                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                        OBSERVABILITY                                  │
│  OTel spans per endpoint → Cloud Trace                              │
│  Trajectory logs: session_id + timestamps → Cloud Logging           │
│  Critic logs: verdict + all 3 metric dimensions                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                         DEPLOYMENT                                    │
│  Google Cloud Run  --min-instances 0  --cpu-throttling              │
│  Secrets: GOOGLE_API_KEY, DEEPGRAM_API_KEY, GOOGLE_APPLICATION_     │
│           CREDENTIALS via Secret Manager                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Latency (benchmarked, `/voice/bench` endpoint)

| Stage | Measured |
|---|---|
| Agent routing (deterministic) | **35ms avg** |
| First TTS audio from transcript | **~400ms** |
| Speech-to-first-audio E2E (incl. Deepgram) | **~600ms** |
| Full TTS loop | **700ms – 1.1s** |

Agent routing is fast because there is no LLM in the orchestration path — routing is pure Python regex + keyword matching. LLM calls only happen inside tools (CV RAG, ATS generation).

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI, Uvicorn |
| **Voice STT** | Deepgram nova-2 (WebSocket streaming) |
| **Voice TTS** | Google Cloud Neural2-D (sentence-level streaming, free tier) |
| **LLM** | Gemini 1.5 Flash (`google-genai`) |
| **Embeddings** | `models/text-embedding-004` |
| **Evaluation** | LLM-as-Judge + 15 golden cases (`ops/eval_data.json`) |
| **Observability** | OpenTelemetry → Cloud Trace + structured trajectory logs |
| **A2A / MCP** | Critic Agent + MCP tool registry |
| **Session state** | SQLite (`/tmp/sessions.db`) |
| **Frontend** | Vanilla JS — text chat + WebSocket voice pipeline |
| **Deployment** | Google Cloud Run (zero-cost optimized) |

---

## Project Structure

```
recruiter-agent/
├── README.md
├── Dockerfile
├── requirements.txt
├── dev.bat                       <-- local dev (Python 3.11, uvicorn --reload)
│
├── app/
│   ├── server.py                 <-- FastAPI routes (/chat, /voice, /mcp/*, /a2a/*)
│   ├── agent.py                  <-- Deterministic orchestrator
│   ├── voice.py                  <-- Voice pipeline (Deepgram STT + Google TTS + barge-in)
│   ├── cv_rag.py                 <-- CV vector search / RAG (Gemini embeddings)
│   ├── tools.py                  <-- Project ranking, static projects, ATS generation
│   ├── github_portfolio.py       <-- Live GitHub portfolio loader (TTL-cached, depth ≤ 1)
│   ├── critic_agent.py           <-- Critic Agent (A2A validator, PASS/FAIL verdicts)
│   ├── judge.py                  <-- LLM-as-Judge (faithfulness, relevancy, factuality)
│   ├── mcp.py                    <-- MCP tool registry + dispatcher
│   ├── session_store.py          <-- SQLite session state
│   ├── quality.py                <-- Trajectory model (steps + timestamps)
│   ├── utils/
│   │   └── normalize.py          <-- Criteria normalization + VALID_CRITERIA registry
│   ├── telemetry/
│   │   ├── tracing.py
│   │   ├── logging.py
│   │   └── metrics.py
│   └── ops/
│       └── eval_runner.py        <-- Eval suite (golden dataset, aggregate metrics)
│
└── frontend/
    └── index.html                <-- Chat UI + WebSocket voice pipeline
```

---

## Voice Pipeline

```
Browser mic (PCM16, 48kHz)
  │
  │  WebSocket /voice?session_id=&sample_rate=
  ▼
Deepgram nova-2
  │  endpointing=150ms, punctuate=true, interim_results=true
  │  is_final transcripts → asyncio.Queue
  ▼
agent_turn()  [35ms]
  ▼
Google Neural2-D TTS
  │  split into sentences → parallel synthesis tasks
  │  stream MP3 chunks over WebSocket as each sentence completes
  ▼
Browser Audio element
  │  onplay  → ttsPlaying=true  (mic sends silence to Deepgram)
  │  onended → ttsPlaying=false (mic sends real audio)
  └  barge-in: RMS > 0.015 → pause audio + send barge_in → tts_cancel.set()
```

**Barge-in flow**: user speaks over TTS → RMS VAD detects in ~85ms → audio paused client-side + `barge_in` sent to server → `asyncio.Event` cancels `_tts_stream` mid-synthesis → `process()` loop free immediately.

**Silence keepalive**: during TTS playback, the ScriptProcessor sends zero-filled PCM16 to Deepgram instead of real mic audio. This prevents the connection from timing out during long responses without sending transcribable audio.

---

## Evaluation Suite

```bash
python -m app.ops.eval_runner --base-url http://localhost:8080
```

15 golden cases covering all pipeline stages. Metrics per case:

| Metric | Range | What it measures |
|---|---|---|
| `score` | 1–5 | Overall reply quality |
| `faithfulness` | 0.0–1.0 | Grounded, no hallucination |
| `relevancy` | 0.0–1.0 | Directly addresses the user input |
| `factuality` | 0.0–1.0 | Specific claims are accurate |

---

## A2A / MCP Endpoints

| Endpoint | Description |
|---|---|
| `POST /a2a/validate` | Submit a turn for critic agent validation |
| `GET  /a2a/summary/{session_id}` | Aggregate quality metrics for a session |
| `GET  /mcp/tools` | Discover available tools and their JSON schemas |
| `POST /mcp/call` | Dispatch a named tool call |

**Available MCP tools:**

| Tool | Description |
|---|---|
| `cv_rag_query` | Answer a question from the CV via RAG |
| `best_projects_for_role` | Return ranked projects for a role + criteria |
| `ats_summary_and_email` | Generate ATS summary + recruiter email |
| `judge_recruiter_turn` | Run LLM judge, return multi-metric scores |

---

## Local Development

```bat
dev.bat
```

Then in browser console:
```js
localStorage.setItem("backendUrl", "http://localhost:8080/chat")
```

Open `http://localhost:8080`. Hot-reload enabled via `uvicorn --reload`.

---

## Deployment

```bash
gcloud run deploy recruiter-agent --source . --region europe-west1
```

**Required secrets in Secret Manager:**
- `GOOGLE_API_KEY` — Gemini API key
- `DEEPGRAM_API_KEY` — Deepgram STT
- `GOOGLE_APPLICATION_CREDENTIALS` — service account JSON for Google Cloud TTS

**Cost-control:**
- `--min-instances 0` — scales to zero, no idle billing
- `--cpu-throttling` — CPU billing stops after each request
- Google Cloud TTS Neural2: 1M characters free/month (resets monthly)
- Deepgram: $200 free credit on signup
