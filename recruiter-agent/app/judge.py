# app/judge.py
from __future__ import annotations

from typing import Dict, Any, List, Optional
import os
import json
import re

from google import genai

from .cv_rag import get_cv_rag
from .tools import get_all_projects, select_best_projects_for_role

GEN_MODEL = "gemini-2.5-flash"          # works for both AI Studio and Vertex AI

_client: "genai.Client | None" = None

# Langfuse v4 — optional, degrades gracefully
try:
    from langfuse import observe, get_client as _lf_get_client
    _HAS_LANGFUSE = True
except ImportError:
    _HAS_LANGFUSE = False
    def observe(*a, **kw):          # type: ignore[misc]
        return lambda f: f
    def _lf_get_client():           # type: ignore[misc]
        return None


def _lf_update(**kwargs) -> None:
    if not _HAS_LANGFUSE:
        return
    try:
        lf = _lf_get_client()
        if lf:
            lf.update_current_generation(**kwargs)
    except Exception:
        pass


def _lf_score(name: str, value: float, comment: str = "") -> None:
    if not _HAS_LANGFUSE:
        return
    try:
        lf = _lf_get_client()
        if lf:
            lf.score_current_trace(name=name, value=value, comment=comment)
    except Exception:
        pass


def _make_client() -> "genai.Client":
    """Build and return a working Gemini client.

    Tries AI Studio key first; falls back to Vertex AI ADC when the key is
    absent, looks like a service-account blob, or fails a quick smoke-test.
    """
    api_key = (os.environ.get("GOOGLE_API_KEY") or "").lstrip("\ufeff").strip()
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "recruiter-sergiu-260213").strip()

    # Try AI Studio key if it looks like a real API key (starts with "AIza")
    if api_key and api_key.startswith("AIza"):
        try:
            client = genai.Client(api_key=api_key)
            # Quick validation \u2014 list models is cheap and auth-gated
            client.models.get(model="gemini-2.5-flash")
            return client
        except Exception:
            pass  # fall through to Vertex ADC

    # Vertex AI ADC \u2014 works on Cloud Run with the default Compute SA
    return genai.Client(vertexai=True, project=project, location="us-central1")


def _ensure_client_configured() -> None:
    global _client
    if _client is not None:
        return
    _client = _make_client()


def _build_grounding_context(role: Optional[str], criteria: Optional[List[str]]) -> str:
    """Give the judge the same candidate evidence the agent is expected to use."""
    try:
        cv_text = get_cv_rag().cv_text.strip()
    except Exception:
        cv_text = "CV evidence unavailable."

    try:
        projects = (
            select_best_projects_for_role(role, criteria or [])
            if role
            else get_all_projects()[:3]
        )
        project_text = "\n".join(
            "- {title}: {summary} | tags: {tags} | impact: {impact}".format(
                title=project.get("title", "Untitled project"),
                summary=project.get("summary", ""),
                tags=", ".join(project.get("tags", [])),
                impact="; ".join(project.get("impact", [])[:3]),
            )
            for project in projects[:3]
        )
    except Exception:
        project_text = "Project evidence unavailable."

    # Keep judge requests bounded while retaining the full candidate evidence first.
    return f"CV:\n{cv_text[:12000]}\n\nRelevant projects:\n{project_text[:5000]}"


@observe(as_type="generation", name="llm_judge")
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
    grounding_context = _build_grounding_context(role, criteria)
    prompt = f"""
You are an expert technical recruiter evaluating an AI recruiter assistant's response.

SYSTEM CONTEXT — read carefully before scoring:
- This assistant helps recruiters evaluate a specific candidate (Sergiu) against a target role.
- The assistant has explicit access to Sergiu's CV and is EXPECTED to share contact details, skills, education, and other CV facts when asked. Sharing this information is the intended, correct behavior — do NOT penalise for privacy reasons.
- When a user has not yet specified a job role, the correct behavior is to ask for the role. Asking "please specify the role" IS the right answer in that situation — score it highly, not as a failure.
- When a user sends a shortcut keyword (e.g. "ats", "1", "another") without a prior role, the correct behavior is to acknowledge the intent and request the missing role.
- Treat the evidence below as the source of truth. For factuality and faithfulness,
  penalise candidate-specific claims that are unsupported or contradicted by it.

Job role: {role or "unknown"}
Evaluation criteria: {crit_text or "not specified"}

User message:
{user_message}

Agent reply:
{agent_reply}

Candidate evidence:
{grounding_context}

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

    # Tell Langfuse what we sent / what model we used
    _lf_update(model=GEN_MODEL, input=prompt, metadata={"role": role, "criteria": criteria or []})

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

    # Log output + per-dimension scores to Langfuse
    _lf_update(output=data)
    for metric in ("faithfulness", "relevancy", "factuality"):
        _lf_score(metric, float(data[metric]), data.get("reasoning", ""))

    return data
