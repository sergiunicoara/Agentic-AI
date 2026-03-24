# app/judge.py
from __future__ import annotations

from typing import Dict, Any, List, Optional
import os
import json
import re

from google import genai

GEN_MODEL = "gemini-2.5-flash"

_client: "genai.Client | None" = None


def _ensure_client_configured() -> None:
    """Create Gemini client once per process."""
    global _client
    if _client is not None:
        return

    api_key = (os.environ.get("GOOGLE_API_KEY") or "").lstrip("\ufeff").strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set.")

    _client = genai.Client(api_key=api_key)


def evaluate_agent_turn(
    role: Optional[str],
    criteria: Optional[List[str]],
    user_message: str,
    agent_reply: str,
) -> Dict[str, Any]:
    """
    Use Gemini as an LLM-judge to rate the agent's reply.

    Returns a structured evaluation with:
    - score: overall 1–5 rating
    - faithfulness: 0.0–1.0 — is the reply grounded and not hallucinating?
    - relevancy:    0.0–1.0 — does it address what the user actually asked?
    - factuality:   0.0–1.0 — are specific claims (projects, skills) accurate?
    - label: excellent | good | mixed | weak | poor
    - issues: list of short issue labels
    - reasoning: brief explanation
    """
    _ensure_client_configured()

    crit_text = ", ".join(criteria or [])
    prompt = f"""
You are an expert technical recruiter evaluating an AI recruiter assistant's response.

SYSTEM CONTEXT — read carefully before scoring:
- This assistant helps recruiters evaluate a specific candidate (Sergiu) against a target role.
- The assistant has explicit access to Sergiu's CV and is EXPECTED to share contact details, skills, education, and other CV facts when asked. Sharing this information is the intended, correct behavior — do NOT penalise for privacy reasons.
- When a user has not yet specified a job role, the correct behavior is to ask for the role. Asking "please specify the role" IS the right answer in that situation — score it highly, not as a failure.
- When a user sends a shortcut keyword (e.g. "ats", "1", "another") without a prior role, the correct behavior is to acknowledge the intent and request the missing role.

Job role: {role or "unknown"}
Evaluation criteria: {crit_text or "not specified"}

User message:
{user_message}

Agent reply:
{agent_reply}

Score each dimension independently:

1. overall score (1–5):
   5 = Excellent  4 = Good  3 = Mixed  2 = Weak  1 = Off-topic or problematic

2. faithfulness (0.0–1.0): Is the reply factually grounded? Does it avoid hallucination?
3. relevancy    (0.0–1.0): Does it directly address what the user asked?
4. factuality   (0.0–1.0): Are specific claims (project names, skills, timelines) accurate?

Respond ONLY as JSON with this exact schema:
{{
  "score": <1–5>,
  "faithfulness": <0.0–1.0>,
  "relevancy": <0.0–1.0>,
  "factuality": <0.0–1.0>,
  "label": "excellent|good|mixed|weak|poor",
  "issues": ["short issue labels"],
  "reasoning": "one or two sentences explaining your rating"
}}
""".strip()

    try:
        resp = _client.models.generate_content(model=GEN_MODEL, contents=prompt)  # type: ignore[union-attr]
        text = getattr(resp, "text", "") or str(resp)
    except Exception as e:
        return {
            "score": 3,
            "faithfulness": 0.5,
            "relevancy": 0.5,
            "factuality": 0.5,
            "label": "mixed",
            "issues": ["judge_call_error"],
            "reasoning": f"Judge failed with {type(e).__name__}: {e}",
        }

    text = text.strip()

    # Strip markdown code fences (gemini-2.5 wraps JSON in ```json ... ```)
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        data = json.loads(text)
    except Exception:
        data = {
            "score": 3,
            "faithfulness": 0.5,
            "relevancy": 0.5,
            "factuality": 0.5,
            "label": "mixed",
            "issues": ["judge_parse_error"],
            "reasoning": text[:200],
        }

    # Ensure complete schema with safe defaults
    data.setdefault("score", 3)
    data.setdefault("faithfulness", 0.5)
    data.setdefault("relevancy", 0.5)
    data.setdefault("factuality", 0.5)
    data.setdefault("label", "mixed")
    data.setdefault("reasoning", data.pop("notes", ""))
    if not isinstance(data.get("issues"), list):
        data["issues"] = []

    # Clamp numeric values to valid ranges
    data["score"] = max(1, min(5, float(data["score"])))
    for dim in ("faithfulness", "relevancy", "factuality"):
        data[dim] = max(0.0, min(1.0, float(data[dim])))

    return data
