# app/judge.py
from __future__ import annotations

from typing import Dict, Any, List, Optional
import os
import json

import google.generativeai as genai

GEN_MODEL = "gemini-1.5-flash"

# simple flag to avoid re-configuring on every call
_client_configured: bool = False


def _ensure_client_configured() -> None:
    """Configure google.generativeai once per process."""
    global _client_configured
    if _client_configured:
        return

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set.")

    genai.configure(api_key=api_key)
    _client_configured = True


def evaluate_agent_turn(
    role: Optional[str],
    criteria: Optional[List[str]],
    user_message: str,
    agent_reply: str,
) -> Dict[str, Any]:
    """
    Use Gemini as an LLM-judge to rate the agent's reply from 1–5 and surface issues.
    """
    _ensure_client_configured()

    crit_text = ", ".join(criteria or [])
    prompt = f"""
You are an expert technical recruiter evaluating an AI assistant's response.

Job role: {role or "unknown"}
Evaluation criteria: {crit_text or "not specified"}

User message:
{user_message}

Agent reply:
{agent_reply}

Evaluate the reply on this 1–5 scale:
- 5: Excellent and highly relevant
- 4: Good, minor issues
- 3: Mixed (some strengths, some weaknesses)
- 2: Weak
- 1: Off-topic, misleading, or problematic

Respond ONLY as JSON with this schema:
{{
  "score": <number 1-5>,
  "issues": ["short issue labels"],
  "notes": "one or two sentences explaining your rating"
}}
""".strip()

    try:
        model = genai.GenerativeModel(GEN_MODEL)
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", "") or str(resp)
    except Exception as e:
        # if judge itself fails, propagate a soft error
        return {
            "score": 3,
            "issues": ["judge_call_error"],
            "notes": f"Judge failed with {type(e).__name__}: {e}",
        }

    text = text.strip()

    try:
        data = json.loads(text)
    except Exception:
        # Fallback: keep something usable
        data = {
            "score": 3,
            "issues": ["judge_parse_error"],
            "notes": text[:200],
        }

    # Ensure minimal schema
    if "score" not in data:
        data["score"] = 3
    if "issues" not in data or not isinstance(data["issues"], list):
        data["issues"] = ["unknown"]
    if "notes" not in data:
        data["notes"] = ""

    return data
