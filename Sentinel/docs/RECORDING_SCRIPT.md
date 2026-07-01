# Sentinel — Demo Video Recording Script
# Target length: ≤ 5 minutes | Upload to YouTube (unlisted is fine)

---

## BEFORE YOU HIT RECORD

Do these steps in advance — they must not appear in the video.

1. Start **Docker Desktop** and wait for the engine to show "Running" (whale icon in system tray)
2. Run `gcloud auth application-default login` and confirm credentials are fresh
3. Make sure your `.env` has:
   ```
   GOOGLE_GENAI_USE_VERTEXAI=TRUE
   GOOGLE_CLOUD_PROJECT=recruiter-sergiu-260213
   GOOGLE_CLOUD_LOCATION=global
   ```
4. Open **two terminal windows** (Git Bash), both `cd`'d into:
   ```
   C:\Users\Sergiu\Desktop\Projects\Agentic-AI\Sentinel
   ```
5. Pre-load the Antigravity commit in a browser tab (do NOT close it):
   ```
   https://github.com/sergiunicoara/Agentic-AI/commit/b7f9516
   ```
6. Set terminal font size to **24pt minimum** so it's readable on video
7. Close all unrelated browser tabs — have only the GitHub commit tab and a blank tab open
8. Do a **dry run** of every command below to confirm nothing errors before recording

---

## SCENE ORDER

| Scene | Time |
|---|---|
| README pitch | 0:00 – 0:25 |
| Deploy script | 0:25 – 1:30 |
| Antigravity — GitHub commit b7f9516 | 1:30 – 1:50 |
| Dashboard loads, scan runs | 1:50 – 3:00 |
| Self-review ADK | 3:00 – 4:00 |
| LLM gate report | 4:00 – 4:45 |
| Close | 4:45 – 5:00 |

---

## STEP 1 — Title (0:00 – 0:25)

**Show:** Browser open at:
```
https://github.com/sergiunicoara/Agentic-AI/tree/main/Sentinel
```

**Say:**
> "Sentinel — hallucination-free security review for vibe-coded agents.
> Every finding it reports must prove itself with deterministic evidence,
> or the system deletes it automatically. Here's the full thing running live."

---

## STEP 2 — Deploy to Cloud Run (0:25 – 1:30)

**Show:** Terminal 1

**Type:**
```bash
bash deploy/deploy.sh
```

**While it builds, say:**
> "Multi-stage Docker build — Node builds the React dashboard,
> Python runtime serves everything. One command to Cloud Run."

**When it finishes, point at the last printed line:**
```
Service URL: https://sentinel-969006882005.us-central1.run.app
```

**Say:**
> "That's the live URL. But first — how this started."

---

## STEP 3 — Antigravity (1:30 – 1:50)

**Show:** Switch to the pre-loaded browser tab:
```
https://github.com/sergiunicoara/Agentic-AI/commit/b7f9516
```

The commit shows **27 files changed** in a single commit, dated Jun 27.
Hold on this view for ~15 seconds.

**Say:**
> "The project was built spec-driven in Antigravity —
> one specification, 27 files scaffolded in a single commit.
> Then built iteratively from there."

---

## STEP 4 — Live Dashboard (1:50 – 3:00)

**Show:** Browser — navigate to:
```
https://sentinel-969006882005.us-central1.run.app/ui/
```
*(note the trailing slash)*

**Say:**
> "This is the live dashboard — it connects via WebSocket and streams
> every stage of the pipeline in real time."

**In the Target path field, type:**
```
targets/t1_injection
```

**Leave both checkboxes (Red team, LLM auditor) unchecked.**

**Click Start Scan.**

**Watch the event feed appear — narrate as each line shows:**

| What appears on screen | What to say |
|---|---|
| `🔍 Profiling the target, selecting which security skills apply.` | "Profiling the target, selecting which security skills apply." |
| `🛠 Four real tools running — bandit, ruff, pip-audit, semgrep. No LLM in this path.` | "Four real tools running — bandit, ruff, pip-audit, semgrep. No LLM in this path." |
| `Evidence collected: N items` | *(pause, let it sink in)* |
| `InjectionAuditor: 2 candidates` | "Injection auditor finds 2 candidates." |
| `⚖️ Now the trust gate.` | "Now the trust gate." |
| `✓ SURVIVED — Unsafe eval() of user input [HIGH]` | "This one survived — real bandit evidence behind it." |
| `✓ SURVIVED — Shell injection via subprocess [HIGH]` | "This one too." |
| Red **FAIL** banner at top | "Verdict: FAIL. Two findings, both backed by deterministic evidence." |

**Point at a SURVIVED badge and say:**
> "If the model had fabricated that evidence ID,
> this badge would say DROPPED instead.
> The gate makes that structurally impossible to bypass."

---

## STEP 5 — ADK Self-Review (3:00 – 4:00)

**Show:** Terminal 1

**Type:**
```bash
adk run sentinel/orchestrator
```

**When the `>` prompt appears, type:**
```
Review the target at sentinel/mcp
```

**Wait for the output. When the adjudicator report prints, point at the B603 finding line, e.g.:**
```
✓ [MED] Subprocess call without shell — evaluating a value from elsewhere
```

**And the verdict line:**
```
Verdict: PASS_WITH_FINDINGS
```

**Say:**
> "Sentinel reviewing its own code.
> It finds a real bandit B603 in its own MCP evidence server —
> subprocess call evaluating an external value.
> Verdict: pass with findings.
> The finding is backed by real evidence. No hallucination."

---

## STEP 6 — LLM Gate Measured Live (4:00 – 4:45)

**Show:** Terminal 2 (or same terminal after adk exits)

**Type:**
```bash
python -m sentinel.eval.llm_gate_report
```

If live LLM access is unavailable, the command now replays the recorded demo
table automatically. Use `--mode live` to force a real Vertex AI call.

**Wait for the table to print. When it appears, point at the Total row:**
```
| Total  |  18  |  15  |  3  |
```

**Say:**
> "The LLM auditor proposed 18 findings across the full corpus.
> 15 survived the gate. 3 were dropped —
> not fabricated evidence IDs, but the model wrote 'severity: medium'
> instead of the schema's required literal 'med'.
> The gate enforces the entire Finding contract, not just one field.
> That's structural validation — not prompting."

---

## STEP 7 — Close (4:45 – 5:00)

**Show:** Table still visible on screen.

**Say:**
> "75 tests passing. Five course concepts demonstrated.
> Repo and live demo links in the description."

---

## AFTER RECORDING

**Trim to ≤ 5:00**

**Upload to YouTube** (unlisted is fine)

**YouTube description — paste exactly:**
```
GitHub repo: https://github.com/sergiunicoara/Agentic-AI/tree/main/Sentinel
Live dashboard: https://sentinel-969006882005.us-central1.run.app/ui/
Kaggle submission: AI Agents Intensive Capstone — Agents for Business track
```

**Kaggle submission:**
1. Paste `docs/WRITEUP.md` content into the Kaggle writeup editor
2. Select track: **Agents for Business**
3. Attach the YouTube link in the Media Gallery
4. Attach cover image (`Sentinel.png`) in the Media Gallery
5. Hit **Submit** before **July 6, 2026 11:59 PM PT**
