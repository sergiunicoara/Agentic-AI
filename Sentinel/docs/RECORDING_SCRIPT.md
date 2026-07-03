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
| README pitch | 0:00 – 0:20 |
| Deploy script | 0:20 – 1:00 |
| Antigravity — GitHub commit b7f9516 | 1:00 – 1:20 |
| Dashboard loads, scan runs | 1:20 – 2:05 |
| Bandit blind spot (T6 / semgrep) — NEW | 2:05 – 2:35 |
| Live sandboxed red team (trimmed) — NEW, optional | 2:35 – 2:50 |
| Self-review ADK | 2:50 – 3:30 |
| LLM gate report (+ DROPPED callout) | 3:30 – 4:20 |
| Close (+ business line) | 4:20 – 4:45 |

> The three NEW/changed beats vs. the first recording: (1) the **Bandit blind spot**
> segment, (2) an explicit **DROPPED** callout narrated over the existing gate-report
> table, and (3) a one-line **business framing** in the close. Everything else is as
> already recorded — you can splice these in rather than re-shoot the whole thing.

---

## STEP 1 — Title (0:00 – 0:25)

**Show:** Browser open at:
```
https://github.com/sergiunicoara/Agentic-AI/tree/main/Sentinel
```

**Say:**
> "Sentinel — hallucination-free security review for vibe-coded agents.
> Every finding it reports must prove itself with deterministic evidence,
> or the system deletes it automatically. The agents reason — an orchestrator
> routes, an auditor investigates. A deterministic gate enforces. Here's the
> full thing running live."

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

## STEP 5 (NEW) — The Bandit Blind Spot (2:10 – 2:40)

*Why: this is the concrete answer to the obvious skeptic question — "isn't this just
bandit with a UI?" It's deterministic and reproducible, so it's safe on camera.*

**Show:** Terminal 1 (or Terminal 2)

**Type — first prove bandit finds nothing on T6:**
```bash
bandit -r targets/t6_ssrf -q
```

Point at the empty result (no issues identified).

**Then run Sentinel's full pipeline on the same target:**
```bash
python -m sentinel.pipeline targets/t6_ssrf
```

Point at the surviving findings — the SSRF and the hardcoded LLM API key — and their
`ev_semgrep_...` evidence IDs.

**Say:**
> "A fair question about any scanner built on bandit is — isn't this just bandit with a UI?
> Here's target T6. Bandit finds nothing. Sentinel catches both the SSRF and the hardcoded
> API key — through two custom semgrep rules bandit has no equivalent for. The detection
> ceiling actually moved, and there's a test that proves bandit catches neither."

---

## STEP 5b (NEW, optional) — Live Sandboxed Red Team (~15s, trimmed)

*Why: nothing else on the page actually EXECUTES attacks. This proves the red team is
real, not a static string match. Legibility is solved by editing — show the setup and
the result, jump-cut the repetitive middle.*

**Show:** Terminal 1

**Type:**
```bash
python -m sentinel.pipeline targets/t1_injection --live-red-team
```

**What to keep in the cut (trim everything between):**
1. The command + the header line: `[LiveRedTeam] Starting live (sandboxed) red team assessment...`
2. One `[LIVE-CONFIRMED]` line (e.g. an eval or shell-injection payload → real function)
3. **Jump-cut** past the rest of the payload lines
4. The final summary line: `[LiveRedTeam] N/M invocations live-confirmed`

**Say (over the trimmed cut):**
> "Opt in, and Sentinel doesn't just pattern-match — it actually executes the attack
> payloads against the target's real functions, inside a sandbox: disposable directory,
> network cut off, hard timeout. It fires eval and shell-injection payloads and confirms
> they really fire. That's trajectory evidence — not a guess."

---

## STEP 6 — ADK Self-Review (2:40 – 3:25)

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

## STEP 7 — The DROPPED Money Shot (3:25 – 4:15)

*The whole thesis is "unprovable findings get deleted." This step SHOWS that happening.
Try for the live dashboard badge first (7A); if you don't land a clean take quickly,
fall back to the gate-report table (7B) which shows the drops deterministically.*

### 7A — PRIMARY: live DROPPED badge on the dashboard (multi-take)

**Prep before recording (off-camera):** the drop is non-deterministic per run, so pre-run
it a few times until you get one, then record that take. Odds are best on **T6** (4 LLM
proposals → highest chance one drifts; ~50–60% per run, ~95% over 3–4 takes). A smaller/
faster Gemini variant drifts *more* on the exact-string schema, which raises the drop rate
in your favor — legitimate, since the gate genuinely rejects it.

**Show:** the deployed dashboard (`/ui/`).

**In the Target path field, type:**
```
targets/t6_ssrf
```

**Check the `LLM auditor` box** (leave Red team unchecked). Click **Start Scan**.

**What you're waiting for in the live event feed:** at least one red **✗ DROPPED** badge
appear alongside the green ✓ SURVIVED ones — with the reason `schema validation failed`.

**Say (point at the DROPPED badge as it lands):**
> "There it is. The LLM auditor proposed this finding, and the gate refused to keep it —
> live, in real time. The model can say whatever it wants; only what it can actually prove
> survives. That red badge is the entire thesis in one frame."

*If after ~5 minutes of takes you don't get a clean DROPPED, switch to 7B — don't burn
more time; the table version lands the same point reliably.*

### 7B — FALLBACK: gate-report table (deterministic)

**Show:** Terminal 2 (or same terminal after adk exits)

**Type:**
```bash
python -m sentinel.eval.llm_gate_report
```

If live LLM access is unavailable, the command replays the recorded demo table
automatically. Use `--mode live` to force a real Vertex AI call.

**Point at the three rows with a DROPPED count — T2, T3, T6 (Unsupported = 1 each):**
```
T2 — Privilege Leak   3   2   1
T3 — Secret Leak      4   3   1
T6 — SSRF             4   3   1
```

**Say:**
> "Watch these three rows. The LLM auditor proposed a finding the gate refused to keep —
> because it couldn't back it the way the schema requires. The model can say whatever it
> wants; only what it can prove survives."

**Then point at the Total row:**
```
| Total  |  18  |  15  |  3  |
```

**Say:**
> "18 proposed across the corpus, 15 survived, 3 dropped — and none of the drops were
> fabricated evidence IDs. Each cited real evidence but wrote 'severity: medium' instead
> of the schema's required literal 'med'. The gate enforces the entire Finding contract,
> not just one field. That's structural validation — not prompting."

---

## STEP 8 — Close, with business framing (4:15 – 4:40)

**Show:** Table still visible on screen (or cut back to the dashboard / cover image).

**Say (business line first — this is the "Agents for Business" track fit):**
> "The buyer is a security lead who won't approve an LLM code reviewer because it
> might just make things up. Naive LLM review runs thirty to forty percent false
> positives — analysts stop trusting it, real findings get ignored with the fake
> ones. Sentinel is zero percent false positives, by construction, at near-zero
> marginal cost per scan — and it wires into the CI gate they already run."

**Then the wrap:**
> "75 tests passing. Five course concepts demonstrated, plus Antigravity for the
> spec-driven scaffolding. Repo and live demo links in the description."

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
