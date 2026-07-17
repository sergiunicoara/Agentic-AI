# recruiter-agent — Demo Script (~4:30)

**The story in one line:** a recruiter doesn't read Sergiu's CV — they *talk to it*.

The demo runs in two acts. **Act I (S01–S04)** is the experience: what a
recruiter sees, says, and walks away with — no terminal, no jargon, just the
product doing its job. **Act II (S05–S09)** is the proof: for the technical
viewer, the same system opened up — real latency numbers, a judge grading
every reply, the test suite with nothing hidden. A recruiter can stop
watching after Act I and have gotten the whole point. An engineer who keeps
watching finds out none of Act I was smoke.

> **Recording notes**
>
> - **Act I** is a browser screen-recording of `frontend/index.html` — use
>   the live URL (`https://recruiter-agent-969006882005.europe-west1.run.app`),
>   it's more honest than localhost and the latency is real. **Turn system
>   audio capture ON** — S03's voice moment is the heart of the demo.
> - **Act II** is Git Bash (POSIX `sh`) on Windows, from the repo root. No
>   `cmd.exe`/PowerShell syntax — no `%VAR%`, no `$env:VAR`. Server starts
>   with `&`, dies with `kill %1`.
> - **Interpreter:** no project venv / `py` launcher on this machine — use
>   the full path `/c/Users/Sergiu/AppData/Local/Programs/Python/Python311/python`
>   (see [`tasks/lessons.md`](../tasks/lessons.md) #11), or your own `python3`.
> - Act II scenes S05–S07 hit the **live Cloud Run deployment**; S08 runs
>   locally. Swap URLs if demoing another environment.

---

# ACT I — The experience

*(~2:15 · browser only · this is the part a hiring manager forwards to a colleague)*

## S01 — Cold open: meet the agent

**Shot:** Browser, full screen, already on the live URL. No terminal anywhere.
Land directly on the hero: the emerald "Live voice AI" badge, the headline,
the chat panel glowing on the right with its green "Ready" dot.

**Action:** Slow cursor drift across the page — badge → headline → chat
panel. Let it breathe for 3 seconds before the V.O. starts.

**V.O.:** "This is Sergiu's CV — except you don't read it. You interview it.
It's a live AI agent that knows his projects, his skills, and his real
metrics, and it's running in production right now. Let me show you what a
recruiter does with it."

---

## S02 — Paste a job description, get a real answer

**Shot:** Same browser. This is the recruiter's actual first move.

**Action (record in order):**
1. Click the quick-prompt **"🎙️ Lead AI Engineer · voice pipeline · RAG ·
   observability"** — a full, realistic job description drops into the input.
   Pause one beat so the viewer sees it's a *real JD*, not a keyword.
2. Hit **Send**. The reply lands as a chat bubble: role confirmed, criteria
   extracted, and a menu — project deep dive, or ATS summary + email.
3. Type `1` and send. The agent returns a **project deep-dive**: a real
   project, with measurable impact mapped to each criterion from the JD.

**Expected on screen:** user bubbles right-aligned, agent bubbles left; the
deep-dive reply names an actual project and ties each criterion ("production
RAG", "observability") to something concrete in it.

**V.O.:** "Paste any job description — this one's a Lead AI Engineer role.
The agent pulls out what the role actually needs, confirms it, and then does
what a good candidate does in a first call: it maps *specific projects with
specific results* to each of your requirements. No generic 'passionate team
player' — it cites work."

---

## S03 — Now say it out loud (the showpiece)

**Shot:** Same page. This is the scene to get right — re-record until the
audio moment lands. System audio ON.

**Action (record in order) — verified against the live deployment, same
session as S02:**
1. Click the **mic icon**. Speak, naturally: *"Next."* The agent advances
   hands-free to the next project deep dive (verified live output: *"Deep
   Dive 3 of 3: AI Engineering Workflow Toolkit…"*).
2. Speak a real CV question: *"Where is he based?"* Verified live reply:
   *"Here's what I found in Sergiu's CV: Sergiu is based in Timisoara,
   Romania."*
3. **Optional, if time allows and it lands clean on the take:** interrupt a
   spoken reply mid-sentence to demonstrate barge-in. This is a real,
   tested feature (7 passing tests in `tests/test_tts_streaming.py`, one of
   which caught a real race condition) — but it's a live audio behavior,
   not something scriptable as guaranteed dialogue, so don't force a
   specific line here. Let it happen naturally and keep whatever take works.

**Expected:** first audio lands fast enough to feel like a phone call, not a
loading screen (measured p50: ~430ms to first audio).

**V.O.:** "And here's the part that separates this from a chatbot: hit the
mic and it's hands-free. Say 'next' to move between projects without
touching the keyboard, or ask a real question about his background — same
backend, same criteria, now spoken out loud."

> **Accuracy note:** an earlier draft of this scene scripted the agent
> giving contextual spoken answers to open-ended follow-up questions
> ("has he shipped retrieval in production, not just a demo?"). Live
> testing against the deployment showed the deterministic router doesn't
> support that — free-form questions either get silently treated as "next"
> or fall back to a generic menu reminder. Only scripted commands
> (`next`/`another`/`ats`) and a narrow set of CV-fact patterns (phone,
> certs, location, etc.) are reliably answered. Use those, not invented
> Q&A, for any live recording.

---

## S04 — Walk away with something you can use

**Shot:** Same chat. The payoff scene — the recruiter's deliverable.

**Action:**
1. Type `ats` (or click the **"📝 ATS summary + recruiter email"** quick
   prompt). Send.
2. The agent returns two artifacts: an **ATS-style candidate summary** and a
   **ready-to-send recruiter email** recommending next steps.
3. Select-all on the email text — the "I could paste this into Outlook right
   now" gesture.

**V.O.:** "And when you're done talking, you don't leave empty-handed. One
word — 'ats' — and you get a summary formatted for your tracking system and
an intro email ready to forward to the hiring manager. The whole loop — JD
in, conversation, deliverable out — took about ninety seconds. That's the
product. Now, if you're technical and wondering whether any of this is
real… stay for act two."

---

# ACT II — The proof

*(~2:15 · terminal + dashboards · for the engineer who stayed)*

## S05 — The latency is measured, not promised

**Shot:** First terminal of the video. Run the benchmark against the **live**
deployment — the one scene where raw numbers beat a clean take.

```bash
/c/Users/Sergiu/AppData/Local/Programs/Python/Python311/python benchmark_voice.py \
  https://recruiter-agent-969006882005.europe-west1.run.app
```

**Expected output (abridged — Stages 2 and 4 are the ones that matter):**
```
Stage 2: Agent turn (POST /chat)
  Agent  : p50=321ms  p95=589ms  min=318ms  max=589ms

Stage 4: E2E WebSocket — agent + TTS (Deepgram excluded)
  msg 1: first_audio=428ms  total=444ms  audio=51200b
  E2E (agent+TTS): p50=428ms  p95=474ms  min=236ms  max=474ms
  Full E2E estimate (incl. ~200ms Deepgram streaming): 628ms
```

**V.O.:** "That half-second voice response you saw in act one? Here's the
receipt. This benchmark runs against the live deployment: 428 milliseconds
median to first audio, measured — the only estimated figure is the
speech-to-text leg, and it's labeled as an estimate on purpose. Every
latency claim in this repo has a script behind it you can re-run."

---

## S06 — Every reply is graded before you see it

**Shot:** Terminal, then 2–3 seconds on `eval_results.json` in an editor.

```bash
/c/Users/Sergiu/AppData/Local/Programs/Python/Python311/python run_eval.py \
  https://recruiter-agent-969006882005.europe-west1.run.app
```

**Expected output (abridged):**
```
Loaded 15 golden cases

{
  "aggregate": {
    "n_cases": 15.0,
    "pass_rate": 1.0,
    "avg_score": 5.0,
    "avg_faithfulness": 1.0,
    "avg_relevancy": 1.0,
    "avg_factuality": 1.0
  }
}
```

**V.O.:** "Everything the agent told you in act one had already been graded
before you saw it. A second model — a judge — scores every reply on three
questions: is it faithful to the real CV, is it relevant to what you asked,
are the facts right. Fifteen golden recruiter conversations replay against
the live agent on every release: fifteen for fifteen, five-point-oh average.
If a change makes the agent worse, the deploy is blocked. Automatically."

---

## S07 — Every conversation leaves a trail

**Shot:** Langfuse (or OTel UI) with one trace expanded — or, if no dashboard
is reachable, the trajectory JSON below. Substitute, don't skip.

```bash
curl -s https://recruiter-agent-969006882005.europe-west1.run.app/session/demo-01/summary | python -m json.tool
```

**Expected output (abridged):**
```json
{
    "session_id": "demo-01",
    "role": "Lead AI Engineer",
    "trajectory": { "steps": [
        {"kind": "tool", "message": "role_extraction"},
        {"kind": "tool", "message": "criteria_parsing"},
        {"kind": "tool", "message": "llm_judge_evaluation",
         "meta": {"score": 5, "faithfulness": 1.0}}
    ]}
}
```

**V.O.:** "Every turn of that conversation left a trace — which step
extracted the role, which parsed the criteria, what the judge scored the
reply. So when I say 'fifteen for fifteen', that's not an anecdote — you can
walk backward from any score to the exact turn that earned it."

---

## S08 — The tests that caught real bugs

**Shot:** Terminal, local repo. A fully green suite — but the V.O. tells the
story of how it *got* green, which builds more trust than the checkmarks.

```bash
/c/Users/Sergiu/AppData/Local/Programs/Python/Python311/python -m pytest tests/ -q
```

**Expected output:**
```
............                                                             [100%]
12 passed, 8 warnings in 49s
```

**V.O.:** "Twelve for twelve — but the interesting part is how it got there.
Seven of these tests cover voice interruption, the feature you saw in scene
three; writing them caught a real race where an already-synthesized sentence
could get dropped mid-interrupt. And two tests here used to *fail* — chasing
those failures exposed an actual routing bug where every GET endpoint,
including the health check, silently returned the web page instead of JSON.
The failing tests weren't noise; they were the map to the bug. Fixed, and
now there's a regression test standing guard so it can't come back."

---

## S09 — Close

**Shot:** Back to the browser — the live page, chat panel ready. Hold 2
seconds, then cut.

```bash
echo "recruiter-agent — live at https://recruiter-agent-969006882005.europe-west1.run.app"
```

**V.O.:** "So: a candidate you can interview before you interview him.
Paste a JD, talk to it, walk away with an ATS summary and an intro email —
and under the hood, measured latency, a judge on every reply, and a test
suite whose failures get chased down to real bugs, not deleted. It's live
right now — link's below. Ask it something hard."

---

## Summary stats

| Metric | Value | Source |
|---|---|---|
| Agent turn latency (p50) | 321ms | `benchmark_voice.py` Stage 2, live Cloud Run |
| First-audio latency (p50) | 428ms | `benchmark_voice.py` Stage 4, live Cloud Run |
| Full E2E voice turn (est.) | ~628ms | Stage 4 p50 + 200ms Deepgram streaming estimate |
| Golden eval pass rate | 100% (15/15) | `run_eval.py` / `eval_results.json` |
| Golden eval avg score | 5.0 / 5.0 | `run_eval.py` / `eval_results.json` |
| Eval pass threshold | ≥ 3.5 / 5.0 | `app/critic_agent.py` |
| Session store (no `REDIS_URL`) | SQLite fallback | `app/session_store.py` |
| Session store (with `REDIS_URL`) | Redis, 24h TTL | `app/session_store.py` |
| API routes exposed | 24 | `app/server.py` (`grep -c "@app\."`) |
| Test suite result | 12 passed / 0 failed | `pytest tests/ -q` — 7 barge-in tests + 5 API tests (incl. route-shadowing regressions) |
| Total runtime | ~4:30 | Act I (S01–S04) + Act II (S05–S09) |

---

## Appendix — cut scenes (still useful for a longer technical demo)

These were scenes in the engineering-first version of this script. They don't
serve the recruiter narrative, but keep them for a deep-dive recording:

- **Cold start / config** — `cat app/config.py`: one required env var
  (`GOOGLE_API_KEY`), port 9191, pydantic settings.
- **Boot + health** — `python -m app.server &` then `curl /health`: OTel,
  structured logging, and Langfuse wired before the first request; `/health`
  doubles as a config readout (shows which session backend is live).
- **Redis → SQLite fallback** — set `REDIS_URL` and `/health` flips from
  `"backend": "sqlite"` to `"backend": "redis"` (24h TTL); drop it or let the
  connection fail and it falls back silently, logged at WARNING. Runtime
  probe in `session_store.py` — no feature flag, no restart branch. *(Don't
  fake a Redis connection on camera if none is running — narrate from code.)*
- **Raw `/chat` via curl** — the S02 conversation as JSON: role extraction →
  criteria parsing → state carried across turns on one `session_id`.
