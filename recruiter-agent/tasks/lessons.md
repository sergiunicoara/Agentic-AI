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

4. **Verify char counts with a script before presenting length-constrained
   text.** First CV bullet attempt was +31/+33 chars over target. Run
   `python -c "print(len(...))"` on every artifact before showing it.

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
