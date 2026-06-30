# Hermes Research Engine

> Multi-agent deep research system — no LangChain, raw OpenAI SDK, deployed on Railway.

**Live demo:** [hermes-research-engine-production.up.railway.app](https://hermes-research-engine-production.up.railway.app)

## What it demonstrates

| Qualification | Implementation |
|---|---|
| Multi-agent orchestration | `OrchestratorAgent` → `SearchAgent` + `RAGAgent` → `SynthesisAgent` |
| ReAct reasoning | Custom loop in `BaseHermesAgent` with native OpenAI tool-calling |
| Agentic memory | Short-term (sliding window), long-term (LanceDB), episodic (JSON store) |
| Tool use / function calling | Web search (DuckDuckGo), RAG retrieval, safe Python eval |
| Observability | `StructuredLogger` (JSON-lines) with `trace_id`, tokens, latency per step |
| Context management | `SlidingWindowMemory` with tiktoken budget enforcement |
| Evaluation framework | `eval/benchmark.py` — 10 questions, 5 scoring criteria, task completion rate |
| MCP-ready | Tool definitions follow JSON Schema (drop-in MCP tool descriptors) |
| FastAPI + SSE | Streaming research via Server-Sent Events with typed event protocol |
| Web UI | Single-page app served at `/` with live agent activity feed |

## Architecture

```
User question (UI or API)
        │
        ▼
OrchestratorAgent (DeepSeek)
  ├── decompose → 2 sub-questions
  ├── [parallel threads]
  │     ├── SearchAgent (DuckDuckGo web search)
  │     └── RAGAgent    (LanceDB retrieval, skipped if KB empty)
  └── SynthesisAgent → final cited Markdown report
        │
        ▼
SSE stream of typed JSON events → UI or curl client
```

Each agent runs a ReAct loop (up to 4 steps): think → call tool → observe → repeat.  
Sub-questions are researched in parallel via `ThreadPoolExecutor`.

## Quick Start

```bash
git clone <repo>
cd hermes-research-engine
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env   # add your API key
python -m uvicorn app.main:app --port 8000
```

Open `http://localhost:8000` for the UI, or use the API directly.

### Environment variables

```env
HF_TOKEN=<your-deepseek-or-openai-compatible-key>
HERMES_MODEL=deepseek-chat
HF_BASE_URL=https://api.deepseek.com/v1
```

Any OpenAI-compatible endpoint works — swap `HF_BASE_URL` and `HERMES_MODEL` to point at Groq, Together, local Ollama, etc.

### Stream a research query

```bash
curl -N "http://localhost:8000/research/stream?question=How+does+RAG+improve+LLM+accuracy"
```

Events stream as newline-delimited JSON:
```
data: {"type": "status", "msg": "Decomposing research question..."}
data: {"type": "decomposed", "sub_questions": ["...", "..."]}
data: {"type": "worker_done", "worker_idx": 0, "sub_q": "..."}
data: {"type": "final_report", "content": "## ..."}
data: {"type": "metrics", "data": {"wall_ms": 42000, "llm_calls": 7, ...}}
```

### Run the evaluation benchmark

```bash
python -m eval.benchmark
```

```
ID     Score   Tokens    Time
-----  ------  ------  ------
Q1     ✓  80%    4,210   12.3s
Q2     ✓  80%    3,890   10.1s
...
Task completion rate: 9/10 (90%)
```

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/health` | Liveness probe |
| `POST` | `/research` | Start async research task → `{task_id}` |
| `GET` | `/research/{task_id}` | Poll task status + result |
| `GET` | `/research/stream?question=...` | SSE stream fresh research (primary endpoint) |
| `POST` | `/memory/ingest` | Add document to knowledge base |
| `GET` | `/memory/search?q=...` | Semantic search knowledge base |
| `GET` | `/episodes` | List past research sessions |

## Deploy to Railway

```bash
railway login
railway init
railway up --service hermes-research-engine
railway vars set HF_TOKEN=<key> HERMES_MODEL=deepseek-chat HF_BASE_URL=https://api.deepseek.com/v1
```

A persistent `/data` volume is mounted automatically for LanceDB and episodic memory.

## Key Design Decisions

- **No LangChain** — raw `openai` SDK + custom ReAct loop gives full control, easier debugging, lower latency
- **Native OpenAI tool-calling** — works with any OpenAI-compatible endpoint (Groq, DeepSeek, Together, Ollama)
- **Parallel workers** — sub-questions researched concurrently via `ThreadPoolExecutor`, not sequentially
- **Skip RAG when empty** — RAGAgent is only invoked when the knowledge base has data, avoiding wasted LLM calls
- **LanceDB embedded** — no separate vector DB service, persists to Railway volume on `/data`
- **SSE typed events** — each event has a `type` field (`status`, `decomposed`, `worker_done`, `final_report`, `metrics`, `error`) for clean UI integration
- **HuggingFace embeddings** — pure HTTP call to `BAAI/bge-small-en-v1.5` via HF Inference API, no local model download
