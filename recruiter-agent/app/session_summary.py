"""
app/session_summary.py — Post-call structured interview summary via Gemini.

Triggered after a voice session ends (or on-demand via GET /session/{id}/summary).
Reads the session's memory trajectory and produces a structured JSON verdict
the recruiter can act on without listening to a recording.

Output schema:
  {
    "session_id":     str,
    "role_fit_score": int 1-5 | null,
    "strengths":      list[str],          # 2-3 items
    "concerns":       list[str],          # 0-2 items
    "recommendation": "Strong Yes" | "Yes" | "Maybe" | "No",
    "summary":        str,                # 2-3 sentence plain-English
    "generated":      bool                # False = Gemini unavailable, used fallback
  }
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_GEN_MODEL = "gemini-2.5-flash"


def generate_session_summary(
    session_id: str,
    memory: List[Dict[str, Any]],
    role: Optional[str],
    criteria: List[str],
    fsm_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a post-call structured interview summary.

    Parameters
    ----------
    session_id:   Voice session identifier (used for logging + response).
    memory:       state.memory events (recruiter_auto_start, set_role, view_project, etc.)
    role:         Job role extracted during the session.
    criteria:     Evaluation criteria used.
    fsm_summary:  Turn-state machine summary (turn_count, interrupted_count, etc.)

    Returns a summary dict. Falls back gracefully if Gemini is unavailable.
    """
    client = _get_gemini_client()
    if client is None:
        return _fallback_summary(session_id, role, criteria)

    transcript = _build_transcript(memory)
    turn_info = _format_turn_info(fsm_summary)

    prompt = f"""You are an AI recruitment assistant. Generate a concise post-call summary for a recruiter.

Role being evaluated: {role or 'Not specified'}
Evaluation criteria: {', '.join(criteria) if criteria else 'Not specified'}
{turn_info}

Session events / transcript:
{transcript}

Return a single JSON object with exactly these fields (no markdown, no extra text):
- "role_fit_score": integer 1-5 (1=poor fit, 5=excellent fit)
- "strengths": array of 2-3 short strings (specific evidence from the session)
- "concerns": array of 0-2 short strings (gaps or open questions)
- "recommendation": one of "Strong Yes", "Yes", "Maybe", "No"
- "summary": 2-3 sentence plain-English paragraph for the recruiter

Base your assessment on the session events. If limited data, use conservative scores."""

    try:
        resp = client.models.generate_content(model=_GEN_MODEL, contents=prompt)
        text = (getattr(resp, "text", "") or "").strip()
        # Strip potential markdown code fences
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(text)
        # Validate and normalise required fields
        parsed = _normalise(parsed)
        parsed["session_id"] = session_id
        parsed["generated"] = True
        logger.info(
            "session_summary_generated | session=%s recommendation=%s score=%s",
            session_id, parsed.get("recommendation"), parsed.get("role_fit_score"),
        )
        return parsed
    except json.JSONDecodeError as exc:
        logger.warning("session_summary: Gemini returned non-JSON (%s)", exc)
        return _fallback_summary(session_id, role, criteria)
    except Exception as exc:
        logger.warning("session_summary: Gemini call failed (%s)", exc)
        return _fallback_summary(session_id, role, criteria)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_gemini_client():
    try:
        from google import genai
        key = (
            os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or ""
        ).lstrip("﻿").strip()
        if not key:
            return None
        return genai.Client(api_key=key)
    except Exception as exc:
        logger.debug("Gemini client unavailable for session summary: %s", exc)
        return None


def _build_transcript(memory: List[Dict[str, Any]]) -> str:
    """Convert memory events to a compact human-readable transcript."""
    lines: List[str] = []
    for event in memory:
        kind = event.get("kind", "")
        payload = event.get("payload", {})

        if kind == "set_role":
            lines.append(f"[Role set] {payload.get('role', '')}")
        elif kind == "set_criteria":
            lines.append(f"[Criteria set] {payload.get('criteria', '')}")
        elif kind == "set_criteria_from_jd":
            lines.append(f"[Criteria from JD] {payload.get('criteria', '')}")
        elif kind == "view_project":
            lines.append(f"[Project viewed] {payload.get('project_id', '')}")
        elif kind == "ats_requested":
            lines.append(
                f"[ATS summary requested] role={payload.get('role', '')} "
                f"criteria={payload.get('criteria', '')}"
            )
        elif kind == "cv_rag_query":
            q = payload.get("question", "")
            a = payload.get("answer", "")[:180]
            lines.append(f"[CV Q&A] Q: {q}")
            lines.append(f"[CV Q&A] A: {a}{'...' if len(payload.get('answer',''))>180 else ''}")
        elif kind == "change_role":
            lines.append(f"[Role changed] old={payload.get('old_role', '')}")
        elif kind == "session_reset":
            lines.append("[Session reset]")
        elif kind == "job_description":
            snippet = payload.get("text", "")[:120]
            lines.append(f"[JD provided] {snippet}...")

    if not lines:
        return "(No conversation events recorded in this session)"
    return "\n".join(lines)


def _format_turn_info(fsm_summary: Optional[Dict[str, Any]]) -> str:
    if not fsm_summary:
        return ""
    return (
        f"Conversation stats: {fsm_summary.get('turn_count', 0)} turns, "
        f"{fsm_summary.get('interrupted_count', 0)} barge-ins "
        f"(interrupt rate {fsm_summary.get('interrupt_rate', 0):.0%})"
    )


def _normalise(d: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure required fields are present and typed correctly."""
    valid_recommendations = {"Strong Yes", "Yes", "Maybe", "No"}

    score = d.get("role_fit_score")
    if not isinstance(score, int) or not (1 <= score <= 5):
        d["role_fit_score"] = None

    if not isinstance(d.get("strengths"), list):
        d["strengths"] = []
    if not isinstance(d.get("concerns"), list):
        d["concerns"] = []

    if d.get("recommendation") not in valid_recommendations:
        d["recommendation"] = "Maybe"

    if not isinstance(d.get("summary"), str):
        d["summary"] = ""

    return d


def _fallback_summary(
    session_id: str,
    role: Optional[str],
    criteria: List[str],
) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "role_fit_score": None,
        "strengths": [],
        "concerns": [],
        "recommendation": "Review manually",
        "summary": (
            f"Session for {role or 'unspecified role'} "
            f"with criteria: {', '.join(criteria) if criteria else 'none specified'}. "
            "Automatic summary unavailable — review session trajectory logs."
        ),
        "generated": False,
    }
