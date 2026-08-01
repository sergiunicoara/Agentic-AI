# Sergiu – AI Recruiter Tour Agent
### Production Voice AI + Multi-Agent System

AI Recruiter is an autonomous voice-first agent that represents a candidate's portfolio to recruiters in real time. Recruiters call in over PSTN or browser voice, where a deterministic multi-agent pipeline extracts the target role, answers CV questions via RAG, ranks relevant projects, and generates ATS-ready summaries — with every reply scored by an LLM-as-a-Judge critic, deployed on Google Cloud Run.

**Live:** https://recruiter-agent-969006882005.europe-west1.run.app

---

## Core Capabilities

- **Deterministic orchestrator** — role extraction → criteria parsing → project ranking → CV Q&A with no LLM in the routing loop (routing logic itself runs in low single-digit ms; see Latency section)
- **Real-time voice pipeline** — Deepgram nova-2 STT over WebSocket → agent → Google Neural2-D TTS with sentence-level streaming. Barge-in via RMS VAD. ~430ms measured agent+TTS first-audio (~600–730ms full voice turn incl. STT endpointing, see Latency section).
- **Streaming LLM→TTS** — Gemini-backed replies (CV RAG) stream token chunks; TTS fires per sentence *as text arrives*, before the full reply is assembled
- **PSTN/SIP telephony** — Twilio Media Streams bridge (`/phone/twiml` + `/phone/stream`): mulaw 8kHz full-duplex, barge-in via Deepgram SpeechStarted + Twilio `clear`
- **WebRTC** — direct browser peer connections via aiortc (`/webrtc/offer`): SDP/ICE negotiation, opus audio, TTS over RTCDataChannel
- **Outbound campaigns** — concurrent dialer with TCPA calling-hours enforcement, GDPR verbal disclosure, opt-out list, exponential backoff retry
- **Turn-taking FSM** — LISTENING → THINKING → SPEAKING → INTERRUPTED per session, with OTel span attributes and interrupt-rate metrics
- **Continuous conversation** — one mic press opens a persistent session; Deepgram auto-detects utterance end, agent responds, TTS streams back. No push-to-talk.
- **CV RAG** — Gemini `text-embedding-004` embeddings over the candidate CV for recruiter Q&A (phone, certifications, location, skills)
- **ATS outputs** — role-matched project deep dives, ATS-style summaries, recruiter email drafts
- **Post-call summaries** — structured interview summary per session (`role_fit_score`, strengths, concerns, recommendation) via `GET /session/{id}/summary`
- **Guardrails** — PII redaction (email/phone/SSN/card) on the logging path + topic enforcement that deflects off-topic messages before they reach the agent
- **LLM-as-Judge** — multi-metric eval per turn: faithfulness, relevancy, factuality (0.0–1.0 each). 6 golden test cases, 100% pass rate, 5.0/5 avg score.
- **Critic Agent (A2A)** — autonomous critic calls the judge via MCP tool interface, issues PASS/FAIL verdicts, tracks session-level quality
- **MCP tool registry** — standard JSON-RPC MCP methods at `/mcp` (`initialize`, `tools/list`, `tools/call`), with protected legacy discovery/dispatch endpoints
- **Langfuse tracing** — every agent turn and judge call traced with input/output/scores in Langfuse dashboard
- **OTel tracing** — every `/chat`, `/voice`, `/mcp/call`, `/a2a/validate` request has a span wired to Cloud Trace
- **Redis session state** — shared store across Cloud Run instances (`REDIS_URL`, 24h TTL) with automatic SQLite fallback

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
      ├── recv: JSON { ready / transcript / reply /                 │
      │               audio_end / audio_cancelled }                 │
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
│    after TTS: drain stale commands, keep freshest only              │
│                                                                      │
│  Google Neural2-D TTS                                               │
│    reply → split sentences → parallel synthesis → MP3 stream        │
│    cancelled: sends audio_cancelled (not audio_end)                 │
│                                                                      │
│  Barge-in: RMS VAD (threshold 0.050) → tts_cancel Event            │
│  Keepalive: zeros sent to Deepgram during TTS playback              │
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
│                                                                      │
│  Langfuse: @observe traces input/output + role/criteria metadata    │
└──────┬───────────────────┬─────────────────────────────────────────┘
       │                   │
┌──────▼──────┐   ┌────────▼──────────────────────────┐
│  cv_rag.py  │   │            tools.py                │
│             │   │                                    │
│  Gemini     │   │  STATIC_PROJECTS (priority):       │
│  embeddings │   │  • Production Voice AI Pipeline    │
│  text-004   │   │  • Agent Observability Dashboard   │
│             │   │  • GraphRAG + RAGAS Pipeline       │
│  Chunk CV   │   │  • AI Engineering Workflow Toolkit │
│  Cosine sim │   │  • AI-Native Data Platform         │
│  Gemini gen │   │                                    │
└─────────────┘   │  GitHub-backed (TTL 6h):           │
                  │  github_portfolio.py               │
                  │  → README.md files, depth ≤ 1     │
                  │  → system files + code filtered    │
                  │                                    │
                  │  ATS summary + email draft         │
                  └────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       EVALUATION LAYER                               │
│                                                                      │
│  judge.py          faithfulness / relevancy / factuality 0.0–1.0   │
│  critic_agent.py   A2A → judge via MCP, PASS/FAIL + session agg.   │
│  eval/run_eval_table.py   6 golden cases → 100% pass, 5.0/5 avg    │
│                                                                      │
│  Langfuse: @observe(as_type="generation") on judge calls            │
│            scores logged per trace (faithfulness/relevancy/factual) │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                         MCP / A2A LAYER                              │
│  /mcp              MCP JSON-RPC: initialize, tools/list, tools/call │
│  /mcp/tools        protected legacy tool discovery                  │
│  /mcp/call         protected legacy tool dispatch                   │
│  /a2a/validate     critic agent endpoint                            │
│  /a2a/summary      session aggregate metrics                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                        OBSERVABILITY                                  │
│  Langfuse  agent_turn traces + llm_judge generations + scores       │
│  OTel      spans per endpoint → Cloud Trace                         │
│  Trajectory logs: session_id + timestamps → Cloud Logging           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                         DEPLOYMENT                                    │
│  Google Cloud Run  --min-instances 0  --cpu-throttling              │
│  Secrets: GOOGLE_API_KEY, DEEPGRAM_API_KEY,                         │
│           GOOGLE_APPLICATION_CREDENTIALS,                           │
│           LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Latency (measured live, `benchmark_voice.py`, n=3)

| Stage | p50 | range |
|---|---|---|
| Agent turn (`POST /chat`, full HTTP round trip) | 321ms | 318 – 589ms |
| Agent + TTS first-audio (`/voice/bench`, Google Neural2-D, Deepgram excluded) | 428ms | 236 – 474ms |
| Agent + TTS full stream complete | 444ms | 327 – 479ms |

Deepgram nova-2 streaming endpointing isn't included above (requires `DEEPGRAM_API_KEY` to benchmark); Deepgram's published nova-2 streaming latency is ~150–300ms, putting a full voice-turn estimate (STT + agent + TTS first-audio) at roughly **580–730ms**.

The deterministic orchestrator itself (role extraction → criteria parsing → project ranking — regex/keyword matching, no LLM call) runs in low single-digit milliseconds in-process. The 300ms+ `/chat` round trip above is dominated by network + Cloud Run request overhead, not the routing logic.

Re-run: `python benchmark_voice.py <cloud-run-url>` (writes `benchmark_voice_results.json`).

---

## Evaluation Results

```
LLM-as-a-Judge Evaluation  |  Recruiter Agent  |  Golden Dataset

Test Case                      Score   Faithful  Relevant  Factual   Label
---------------------------------------------------------------------------
Role extraction — voice AI     5.0/5   1.00      1.00      1.00      excellent  PASS
Criteria parsing — observ.     5.0/5   1.00      1.00      1.00      excellent  PASS
Project deep dive — RAG        5.0/5   1.00      1.00      1.00      excellent  PASS
CV Q&A — certifications        5.0/5   1.00      1.00      1.00      excellent  PASS
ATS summary quality            5.0/5   1.00      1.00      1.00      excellent  PASS
Shortcut without role guard    5.0/5   1.00      1.00      1.00      excellent  PASS
---------------------------------------------------------------------------
AVERAGE                        5.0/5   1.00      1.00      1.00                 100% pass

Model: Gemini 2.5 Flash  ·  6 test cases  ·  metrics: faithfulness / relevancy / factuality
```

Run yourself:
```bash
python eval/run_eval_table.py
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI, Uvicorn |
| **Voice STT** | Deepgram nova-2 (WebSocket streaming, 150ms endpointing) |
| **Voice TTS** | Google Cloud Neural2-D (sentence-level streaming, free tier) |
| **LLM** | Gemini 2.5 Flash (`google-genai`) |
| **Embeddings** | `models/text-embedding-004` |
| **Evaluation** | LLM-as-Judge + 6 golden cases, 100% pass rate |
| **LLM Observability** | Langfuse (traces, scores, generations) |
| **Infra Observability** | OpenTelemetry → Cloud Trace + structured logs |
| **A2A / MCP** | Critic Agent + MCP tool registry (4 named tools) |
| **Telephony** | Twilio Media Streams (PSTN/SIP, mulaw 8kHz) + WebRTC via aiortc |
| **Guardrails** | PII redaction + topic enforcement (`guardrails.py`) |
| **Session state** | Redis (`REDIS_URL`, 24h TTL) → SQLite fallback (`/tmp/sessions.db`) |
| **Frontend** | Vanilla JS — text chat + WebSocket voice pipeline |
| **Deployment** | Google Cloud Run (`--timeout=3600 --min-instances=1` for WebSocket sessions) |

---

## Voice Pipeline

```
Browser mic (PCM16, 48kHz)
  │
  │  WebSocket /voice?session_id=&sample_rate=
  ▼
Deepgram nova-2
  │  endpointing=150ms, utterance_end_ms=1000, punctuate=true
  │  is_final transcripts → asyncio.Queue
  ▼
agent_turn()
  ▼
Google Neural2-D TTS
  │  split into sentences → parallel synthesis tasks
  │  stream MP3 chunks over WebSocket as each sentence completes
  │  cancelled → sends audio_cancelled (client discards buffer, no playback)
  ▼
Browser Audio element
  │  onplay  → ttsPlaying=true  (mic sends silence to Deepgram)
  │  onended → ttsPlaying=false (mic sends real audio)
  └  barge-in: RMS > 0.050 → pause audio + send barge_in → tts_cancel.set()
```

**Barge-in flow**: user speaks over TTS → RMS VAD detects in ~85ms → audio paused client-side + `barge_in` sent to server → `asyncio.Event` cancels `_tts_stream` mid-synthesis → server sends `audio_cancelled` → client discards in-flight bytes → `process()` loop free immediately.

**Silence keepalive**: during TTS playback the ScriptProcessor sends zero-filled PCM16 to Deepgram instead of real mic audio. This prevents connection timeout during long responses without sending transcribable audio.

**audio_cancelled protocol**: interrupted TTS sends `audio_cancelled` (not `audio_end`). Client only calls `playAudioChunks()` on `audio_end`, so stale bytes from cancelled streams are never played and never re-set `ttsPlaying=true`.

---

## Telephony Endpoints

| Endpoint | Description |
|---|---|
| `POST /phone/twiml` | Twilio inbound-call webhook — returns TwiML connecting to `/phone/stream` |
| `WS   /phone/stream` | Twilio Media Streams WebSocket (mulaw 8kHz, full duplex, barge-in) |
| `POST /webrtc/offer` | WebRTC SDP offer → answer (aiortc, full ICE; needs UDP — not Cloud Run) |
| `DELETE /webrtc/{pc_id}` | Explicit peer connection cleanup |
| `POST /outbound/campaign` | Create outbound call campaign (E.164 numbers, concurrency cap) |
| `POST /outbound/campaign/{id}/start` | Start dialing (TCPA hours + opt-out enforced) |
| `POST /outbound/opt-out` | Permanent opt-out for a number |
| `POST /outbound/callback` | Twilio status callback (ringing/answered/completed/failed) |
| `GET  /outbound/status` | Live concurrency stats + per-campaign aggregates |

## Session & Health Endpoints

| Endpoint | Description |
|---|---|
| `GET /session/{session_id}/summary` | Post-call structured interview summary (cached, on-demand fallback) |
| `GET /health` | Liveness + session store backend info (redis/sqlite) |

## A2A / MCP Endpoints

| Endpoint | Description |
|---|---|
| `POST /a2a/validate` | Submit a turn for critic agent validation |
| `GET  /a2a/summary/{session_id}` | Aggregate quality metrics for a session |
| `POST /mcp` | MCP JSON-RPC endpoint (`initialize`, `tools/list`, `tools/call`) |
| `GET  /mcp/tools` | Discover available tools and their JSON schemas |
| `POST /mcp/call` | Dispatch a named tool call |

**Available MCP tools:**

| Tool | Description |
|---|---|
| `cv_rag_query` | Answer a question from the CV via RAG |
| `best_projects_for_role` | Return ranked projects for a role + criteria |
| `ats_summary_and_email` | Generate ATS summary + recruiter email |
| `judge_recruiter_turn` | Run LLM judge, return faithfulness/relevancy/factuality |

**A2A flow**: `POST /a2a/validate` → `critic_agent.validate_turn()` → `call_mcp_tool("judge_recruiter_turn")` → Gemini judge → PASS/FAIL verdict + recommended actions + session aggregate metrics. The critic never imports the judge directly — it calls it through the MCP interface, the same way any external agent would.

---

## Langfuse Observability

Every conversation turn is traced in Langfuse:

| Trace | What's captured |
|---|---|
| `agent_turn` | Input message, role, criteria, output reply |
| `llm_judge` (generation) | Full prompt → Gemini 2.5 Flash, output JSON |
| Scores | `faithfulness`, `relevancy`, `factuality` attached to each trace |

Required env vars (set via Cloud Run secrets or `.env`):
```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

Langfuse is optional — the agent degrades silently to no-ops when keys are absent.

---

## Project Structure

```
recruiter-agent/
├── README.md
├── Dockerfile
├── requirements.txt
│
├── app/
│   ├── server.py                 FastAPI routes (/chat, /voice, /phone/*, /webrtc/*, /outbound/*, /mcp/*, /a2a/*)
│   ├── agent.py                  Deterministic orchestrator (@observe) + agent_turn_stream()
│   ├── voice.py                  Voice pipeline (Deepgram STT + streaming TTS + barge-in)
│   ├── phone.py                  Twilio Media Streams bridge (PSTN/SIP, mulaw 8kHz)
│   ├── webrtc.py                 WebRTC peer connections (aiortc, SDP/ICE, data channel)
│   ├── outbound.py               Outbound campaign manager (TCPA/GDPR, backoff retry)
│   ├── turn_state.py             Turn-taking FSM (LISTENING/THINKING/SPEAKING/INTERRUPTED)
│   ├── guardrails.py             PII redaction + topic enforcement
│   ├── session_summary.py        Post-call structured interview summary (Gemini)
│   ├── voice_livekit.py          LiveKit Agents adapter (optional, guarded import)
│   ├── cv_rag.py                 CV vector search / RAG (Gemini embeddings + query_stream)
│   ├── tools.py                  Project ranking, static projects, ATS generation
│   ├── github_portfolio.py       Live GitHub portfolio loader (TTL-cached, depth ≤ 1)
│   ├── critic_agent.py           Critic Agent (A2A validator, PASS/FAIL verdicts)
│   ├── judge.py                  LLM-as-Judge (@observe as_type=generation)
│   ├── mcp.py                    MCP tool registry + dispatcher
│   ├── session_store.py          Redis session state (SQLite fallback)
│   ├── quality.py                Trajectory model (steps + timestamps)
│   ├── utils/
│   │   └── normalize.py          Criteria normalization + VALID_CRITERIA registry
│   └── telemetry/
│       ├── tracing.py            OTel tracer setup
│       ├── logging.py            Structured logging
│       └── langfuse_setup.py     Langfuse client init + flush
│
├── eval/
│   ├── run_eval_table.py         Golden dataset runner (6 cases, color-coded table)
│   ├── run_wer_eval.py           WER harness (Google TTS → Deepgram → word error rate)
│   └── compare_versions.py       A/B eval between two Cloud Run revisions (delta table)
│
└── frontend/
    └── index.html                Chat UI + WebSocket voice pipeline
```

---

## Local Development

```bash
uvicorn app.server:app --reload --port 8080
```

Then in browser console:
```js
localStorage.setItem("backendUrl", "http://localhost:8080/chat")
```

Open `http://localhost:8080`.

---

## Deployment

```bash
gcloud run deploy recruiter-agent --source . --region europe-west1 \
  --allow-unauthenticated --timeout=3600 --min-instances=1
```

`--timeout=3600` keeps long voice WebSocket sessions alive; `--min-instances=1` avoids cold-start latency on the first call.

**Required secrets:**
- `GOOGLE_API_KEY` — Gemini API key
- `INTERNAL_API_KEY` — required by `/mcp` and `/a2a` endpoints; pass it as `X-Internal-Api-Key`
- `DEEPGRAM_API_KEY` — Deepgram STT
- `GOOGLE_APPLICATION_CREDENTIALS` — service account JSON for Google Cloud TTS
- `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` — Langfuse (optional, traces disabled if absent)
- `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` + `TWILIO_FROM_NUMBER` — telephony (optional, phone endpoints inactive without them)
- `REDIS_URL` — Redis session store (optional, falls back to SQLite if absent)

**Known limits:**
- WebRTC (`/webrtc/offer`) will not establish media on Cloud Run — UDP is blocked, so ICE fails. Use LiveKit Cloud, a GCE VM, or Fly.io for WebRTC. The Twilio bridge works fine (TCP WebSocket).
- Outbound campaign state is in-memory — lost on instance restart/scale-out. Production fix: Firestore or Cloud SQL.

**Cost:**
- Cloud Run: `--min-instances=1` keeps one warm instance billed; drop to 0 for zero-cost idle
- Google Cloud TTS Neural2: 1M characters/month free
- Deepgram: $200 free credit on signup
- Langfuse: free tier (50k observations/month)
