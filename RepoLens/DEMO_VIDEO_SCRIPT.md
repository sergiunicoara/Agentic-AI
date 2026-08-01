# Codex Code Documentation Assistant — E2E Demo Script

Target length: 4–4.5 minutes
Format: 16:9 screen recording, 1080p, browser + terminal  
Voice: calm, confident, conversational; approximately 135 words per minute  
Music: optional low-volume ambient bed; keep the product audio and narration clear

## Recording preparation

Start the application with the existing local configuration. Do not show the configuration
file or any credential values during recording:

```powershell
docker compose up --build
```

Open these tabs before recording:

- Application: [http://localhost:3000](http://localhost:3000)
- API health: [http://localhost:8000/health](http://localhost:8000/health)
- Database health: [http://localhost:8000/health/db](http://localhost:8000/health/db)
- GitHub repository: [project repository](https://github.com/NP-Assignments-Labs/fde-sergiu-nicoara-cc9e6d4f)
- GitHub Actions: [CI runs](https://github.com/NP-Assignments-Labs/fde-sergiu-nicoara-cc9e6d4f/actions)
- Langfuse (optional): open the project dashboard only if it is already configured.

Use a clean browser window, hide unrelated tabs, and increase the browser zoom to 110%.
Do not display `.env`, API keys, terminal environment variables, or credential values.

## Scene 0 — Ingestion completes the workflow (0:00–0:25)

### Screen

Show a short, pre-recorded terminal segment of this command completing. Keep the final file and
chunk summary visible, but do not show any configuration or environment values:

```powershell
docker compose run --rm api python -m app.ingest https://github.com/fastapi/fastapi.git --subdir fastapi
```

### Voiceover

> The workflow starts by ingesting a repository from GitHub or a local path. The pipeline respects
> ignore rules, parses Python into AST-aware chunks, splits Markdown by headings, creates embeddings,
> and stores the exact source needed for later citation verification.

## Scene 1 — Product and health check (0:25–0:40)

### Screen

Show the terminal briefly, then open the application. If useful, open the health endpoints in
separate tabs and return immediately to the application.

### Voiceover

> This is Codex, a code documentation assistant. It ingests a repository, retrieves the most
> relevant code using AST-aware chunks and vector search, then answers with citations that can
> be opened against the original source. The stack is containerized with a Next.js frontend,
> FastAPI backend, and Postgres with pgvector.

### On-screen detail

Show successful HTTP 200 health responses, then the main application.

## Scene 2 — Repository selection and map (0:40–1:05)

### Screen

1. Show the repository selector.
2. Select the FastAPI demo repository.
3. Expand the repository map tree.
4. Point out Python packages and Markdown files.

### Voiceover

> The default demo repository is FastAPI. The repository map is generated from the indexed
> files, so the user can understand the corpus before asking a question. The same ingestion
> pipeline also accepts a GitHub URL or a local repository path.

### Detail link

Use the repository map in the application. The supporting implementation is in
`backend/app/browse/repo_map.py`.

## Scene 3 — Source viewer and exact content (1:05–1:30)

### Screen

1. Expand `fastapi/routing.py` in the repository map.
2. Click the `APIRouter` symbol to open its source range.
3. Scroll to show syntax-highlighted source content.
4. Keep the file path and line numbers visible.

### Voiceover

> Files are stored with their exact source content. This makes a citation verifiable rather
> than decorative: clicking a citation opens the corresponding repository file and line range.

### Detail link

Use the source viewer in the application. The API endpoint is:

```text
GET http://localhost:8000/file?repo_id=<selected-repo-id>&path=<file-path>
```

## Scene 4 — RAG chat, streaming citations, and memory (1:30–2:25)

### Screen

Ask these questions one at a time:

```text
Where is APIRouter defined and what does it inherit from?
```

Then:

```text
How does FastAPI create and configure the application object?
```

Then ask one short follow-up:

```text
Give me a shorter summary of that.
```

Capture the streaming response as it appears. Click one returned citation and show the source
viewer opening the exact cited range.

### Voiceover

> The assistant retrieves relevant chunks, assembles a bounded context, and streams the answer
> as server-sent events. The follow-up uses the repository-scoped conversation history. Supported
> factual claims cite a file and exact line range.
The backend validates returned citations against the chunks that were actually supplied to the
model, so invented paths and line ranges are discarded.

### Detail links

- Chat UI: `frontend/app/components/ChatPanel.tsx`
- Retrieval: `backend/app/retrieval/search.py`
- Citation validation: `backend/app/retrieval/citations.py`
- Chat orchestration: `backend/app/retrieval/service.py`

## Scene 5 — Grounded refusal (2:25–2:45)

### Screen

Ask a question that is outside the indexed repository:

```text
What is the production database password used by FastAPI?
```

Show that the assistant refuses to guess and does not fabricate a citation.

### Voiceover

> When the repository does not contain the answer, the assistant says so instead of guessing.
This refusal behavior is part of the evaluation suite, not just a prompt-level aspiration.

## Scene 6 — MCP capability (2:45–3:10)

### Screen

Show the committed `.mcp.json` file and the MCP server entry briefly. If an MCP-capable client
is available, run or show the three tools:

- `search_code`
- `get_file`
- `get_repo_map`

### Voiceover

> The same retrieval and browsing capabilities are exposed through MCP. That means an MCP
> client can search code, retrieve a file, and inspect the repository map without duplicating
> the application logic.

### Detail links

- MCP configuration: `.mcp.json`
- MCP server: `backend/app/mcp_server.py`

## Scene 7 — Evaluation, CI, and observability (3:10–3:50)

### Screen

1. Open `evals/golden.yaml` briefly.
2. Open the GitHub Actions workflow.
3. Show a green CI run with migrations 001–004, backend, deterministic objective evaluation
   tests, and frontend jobs.
4. If Langfuse is configured, open it and show one trace without exposing keys; otherwise show
   the local OpenTelemetry console trace.

### Voiceover

> Quality is measured with a golden question set covering retrieval, answer correctness, citation
validity and coverage, groundedness, refusal accuracy, and latency. CI runs deterministic objective
evaluation tests, while the frontend is type-checked and production-built. OpenTelemetry and optional
Langfuse instrumentation provide visibility into ingestion, retrieval, generation, and MCP calls.

### Detail links

- Golden set: `evals/golden.yaml`
- CI workflow: `.github/workflows/ci.yml`
- Evaluation results: `evals/results/20260731T143844Z.json`
- Observability: `backend/app/observability.py`
- Langfuse console: use the configured `LANGFUSE_BASE_URL`

## Scene 8 — Close (3:50–4:10)

### Screen

Return to the application with the repository map, a cited answer, and the source viewer visible
in a clean final layout. Then transition to a dedicated closing card with the project name and
three short proof points: **Grounded. Verifiable. Observable.**

### Voiceover

> Codex turns a repository into a transparent, testable knowledge experience: ingest, retrieve,
explain, and verify. Every answer can lead back to source, every claim is evaluated, and the
workflow is observable from end to end. A focused engineering system, ready for review.

### Final links

- [GitHub repository](https://github.com/NP-Assignments-Labs/fde-sergiu-nicoara-cc9e6d4f)
- [GitHub Actions](https://github.com/NP-Assignments-Labs/fde-sergiu-nicoara-cc9e6d4f/actions)
- [Assignment submission](https://apply.newpage.io/submit-assignment/cc9e6d4f-94a7-4641-9f77-1965028d14ee)

## Recording checklist

- Hide `.env`, API keys, browser passwords, and personal account information.
- Show the completed ingestion summary before opening the application; do not wait through a live
  clone or embedding run during the recording.
- Keep the repository selector, citation, source viewer, and CI result readable.
- Record each question once; avoid long pauses while indexing or loading.
- Use captions for the three key terms: `AST-aware chunks`, `validated citations`, and `MCP`.
- Export as MP4, H.264, 1080p, 30 fps.
