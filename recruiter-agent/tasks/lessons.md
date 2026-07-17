# Lessons Learned — recruiter-agent

Patterns from corrections in past sessions. Review at session start.

## Accuracy of claims (CV / marketing copy)

1. **Audit copy against actual data flow, not vibes.** The overview claimed
   "candidate pre-screening" but the agent *represents the candidate* and serves
   recruiters — the direction was inverted. Before writing any product/CV
   description, trace who calls whom in the code (`agent_turn` serves the
   recruiter; the CV/RAG content belongs to the candidate).

2. **Name features by what they actually do.** "LLM-as-a-Judge fit scoring"
   conflated two separate things: the judge (`critic_agent.py`) scores *agent
   reply quality* (faithfulness/relevancy/factuality); fit scoring lives in the
   session summary (`role_fit_score`) and the deterministic project ranker.
   A recruiter who tries the product would notice the mismatch.

3. **Only claim what is live in the deployed revision.** "Redis session state"
   is honest only because the code probes `REDIS_URL` first — but the deployed
   service has no `REDIS_URL` set, so the fallback (SQLite) is what actually
   runs. Flag this gap whenever copy and deployment diverge.

3a. **A latency table needs a re-runnable script behind every cell.** README's
    "35ms agent routing / ~400ms TTS / ~600ms TTFA / 700ms-1.1s full loop" table
    didn't match `benchmark_voice_results.json` at all — "~600ms" turned out to
    be `median(measured) + 200ms` (a hard-coded Deepgram guess), and "35ms" /
    "~400ms" had no measurement behind them anywhere in the repo. Fixed by
    re-running `benchmark_voice.py` against the live Cloud Run URL and replacing
    every cell with the actual p50/range from that run, with estimates clearly
    labeled as estimates. Before publishing any latency/perf number, find the
    script that produces it and run it — don't trust a number that "sounds
    derived from" a benchmark.

4. **Verify char counts with a script before presenting length-constrained
   text.** First CV bullet attempt was +31/+33 chars over target. Run
   `python -c "print(len(...))"` on every artifact before showing it.

4a. **A stale number lives in more than the docs — grep the whole repo,
    including code that generates live output.** The "~600ms TTFA / 35ms
    routing" figure from lesson 3a turned out to be duplicated in four
    separate places: `README.md`, `app/tools.py` (STATIC_PROJECTS, recited
    to recruiters in project deep-dives), `frontend/index.html` (the actual
    UI copy), and — worst — `app/agent.py`'s `low_latency` criteria-match
    branch, which builds text sent live through `/chat` whenever a recruiter
    mentions "low latency" as a criterion. That last one isn't documentation
    at all; it's a runtime f-string a real user reads. Same session also
    found `frontend/index.html` citing `RAGAS context_precision=1.0` — a
    metric that belongs to a *different* STATIC_PROJECTS entry
    (`graphrag:ragas-pipeline`), not this project's actual eval (Gemini
    LLM-as-Judge, pass_rate/avg_score). Fix: after finding one stale number,
    `grep -rn "<the number>" --include="*.py" --include="*.html" --include="*.md" .`
    across the whole repo before considering the fix done — don't stop at
    the first file that had the bug, and don't assume docs are the only
    place a claim can be wrong. Prompt-generation code (agent.py, tools.py)
    is a live surface, not a doc, and is easy to skip because it doesn't
    "look like" copy.

## Stale docs

5. **Update README in the same change that ships the feature.** The entire
   telephony layer (Twilio, WebRTC, outbound), the FSM, and P1–P4 were live
   for a full session before the README mentioned any of it. Stale latency
   claims ("sub-200ms") survived in docstrings for weeks until an audit caught
   them.

## Windows / tooling

6. **gcloud: never trust a remembered project ID.** Deploy failed with
   PERMISSION_DENIED on a stale project id. Run `gcloud projects list` first.
   Correct project: `recruiter-sergiu-260213` (number 969006882005).

7. **gcloud runs only via PowerShell with the full path**
   `& "C:\Users\Sergiu\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"` —
   it is not on the bash sandbox PATH, and the `&` call operator is a bash
   syntax error (use the PowerShell tool, not Bash).

8. **PowerShell has no heredocs.** `git commit -m "$(cat <<'EOF'...)"` fails.
   Use here-strings: `git commit -m @'...'@` with the closing `'@` at column 0.

9. **Windows terminals default to cp1252.** Any Python script printing `→`,
   `—`, or emoji needs `sys.stdout.reconfigure(encoding="utf-8")` at the top.

10. **Read a file before Edit.** The Edit tool rejects edits to unread files —
    read first, every time, even for "obvious" one-liners.

11. **No project-local Python on this machine; `py` launcher isn't on PATH.**
    `py -3.11 benchmark_voice.py ...` from the script's own docstring fails.
    Use the venv at `C:\Users\Sergiu\Desktop\Projects\Vetto\venv\Scripts\python`
    (has httpx + websockets) via the Bash tool. It lacks
    `google-cloud-texttospeech` / `google-cloud-secretmanager` — Stage 1
    (Deepgram) and Stage 3b (Google TTS direct) get skipped, but Stage 2
    (`/chat`) and Stage 4 (`/voice/bench` E2E, real production TTS) still run
    and are the most relevant numbers anyway.
