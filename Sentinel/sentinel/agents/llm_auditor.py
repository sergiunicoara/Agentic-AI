"""
LLM Auditor — the one specialist whose findings can actually hallucinate.

Every other auditor (Injection, Privilege, SupplyChain, RedTeam) is a
deterministic lookup table over tool output: it cannot propose a finding
without a real evidence_id, so the Adjudicator never has anything to drop
from them. This auditor is different — it shows the evidence store and the
raw source to Gemini and asks it to reason about risks freeform. That
freedom is exactly what makes hallucination possible, and exactly why this
is the auditor whose output the Adjudicator gate actually has to defend
against in normal operation.

Opt-in only (pipeline's include_llm_auditor=False by default) — it costs
an API call and requires Vertex AI credentials, so it never runs in the
deterministic eval/test path. If credentials aren't configured or the
call fails for any reason, this returns an empty candidate list rather
than raising — the rest of the pipeline must not depend on this auditor.
"""
import json
import os
from pathlib import Path

from sentinel.models.schemas import Evidence, PILLARS

MODEL_NAME = os.environ.get("SENTINEL_LLM_AUDITOR_MODEL", "gemini-2.5-flash")

SYSTEM_PROMPT = """You are a security auditor reviewing a software agent's source code.

You will be given:
1. The target's source code
2. A list of deterministic evidence items already collected by static
   analysis tools (bandit, ruff, pip-audit), each with a unique evidence_id

Propose security findings for risks you see in the source code. Every
finding you propose MUST cite at least one evidence_id from the provided
list that supports it — do not invent evidence_ids, and do not propose a
finding with no supporting evidence_id. If you believe there is a real
risk but no evidence item supports it, do not report it; say nothing
rather than report it without an evidence_id.

Respond with ONLY a JSON array (no markdown fences, no prose) of objects
with exactly these fields:
  finding_id (string, unique), pillar (int 1-7), severity (one of
  "low","med","high","critical"), confidence (float 0-1), title (string),
  rationale (string), evidence_ids (array of strings — must be from the
  provided list), remediation (string).

If there is nothing to report, respond with an empty JSON array: []
"""


def _build_prompt(target_path: str, evidence_list: list[Evidence]) -> str:
    target = Path(target_path)
    code_chunks = []
    for py_file in sorted(target.rglob("*.py")):
        try:
            code_chunks.append(f"--- {py_file} ---\n{py_file.read_text(encoding='utf-8', errors='ignore')}")
        except Exception:
            continue

    evidence_summary = [
        {"evidence_id": e.evidence_id, "source": e.source, "locator": e.locator, "raw": e.raw}
        for e in evidence_list
    ]

    pillar_legend = "\n".join(f"  {k}: {v}" for k, v in PILLARS.items())

    return (
        f"Pillar legend:\n{pillar_legend}\n\n"
        f"Evidence available (evidence_id values you may cite):\n"
        f"{json.dumps(evidence_summary, indent=2)}\n\n"
        f"Source code:\n" + "\n\n".join(code_chunks)
    )


def audit_with_llm(evidence_list: list[Evidence], target_path: str) -> list[dict]:
    """
    Ask Gemini to propose candidate findings for the target. Returns
    candidate dicts in the same shape every other auditor produces —
    the Adjudicator treats this auditor's output identically to the
    deterministic ones, dropping anything that fails the evidence check.
    """
    try:
        from google import genai
    except ImportError:
        return []

    try:
        client = genai.Client(
            vertexai=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE",
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        )
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=_build_prompt(target_path, evidence_list),
            config={"system_instruction": SYSTEM_PROMPT, "temperature": 0.2},
        )
        raw_text = (response.text or "").strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text

        candidates = json.loads(raw_text)
        if not isinstance(candidates, list):
            return []
        return candidates
    except Exception as e:
        print(f"[LLMAuditor] Skipped — {type(e).__name__}: {e}")
        return []
