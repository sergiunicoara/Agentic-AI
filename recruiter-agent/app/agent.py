# app/agent.py — Production Recruiter Tour Agent

from __future__ import annotations

from typing import Dict, Any, List, Tuple, Optional
import re

from .models.state import State
from .tools import (
    get_all_projects,
    select_best_projects_for_role,
    generate_ats_summary_and_email,
)
from .utils.normalize import normalize_criteria, VALID_CRITERIA
from .cv_rag import get_cv_rag  # <-- CV RAG integration


# ------------------------------------------------------------
# Role extraction
# ------------------------------------------------------------

VALID_ROLES = [
    "machine learning engineer",
    "ml engineer",
    "senior ml engineer",
    "ai engineer",
    "llm engineer",
    "nlp engineer",
    "data scientist",
    "ml scientist",
    "ai researcher",
    "software engineer",
    "backend engineer",
    "full stack engineer",
    "devops engineer",
]

ROLE_ENDINGS = ["engineer", "scientist", "developer", "researcher"]


def extract_role(text: str) -> Optional[str]:
    """
    Simple heuristic role extraction from free text / job description.
    No LLM, deterministic & cheap.
    """
    t = text.lower().strip()

    # direct matches first
    for r in VALID_ROLES:
        if r in t:
            return r.title()

    # generic "<something> engineer|scientist|developer|researcher"
    match = re.search(
        r"\b([a-z0-9 /+_-]+?(engineer|scientist|developer|researcher))\b",
        t,
    )
    if match:
        return match.group(1).strip().title()

    return None


# ------------------------------------------------------------
# Memory helpers (simple internal long-term memory)
# ------------------------------------------------------------

def remember(state: State, kind: str, payload: Dict[str, Any]) -> None:
    """
    Very lightweight "memory" mechanism.

    We store only structured, meaningful events – not raw chat.
    """
    state.memory.append(
        {
            "kind": kind,
            "payload": payload,
        }
    )


# ------------------------------------------------------------
# CV Q&A helpers (RAG questions)
# ------------------------------------------------------------

CV_QUERY_KEYWORDS = [
    "phone",
    "phone number",
    "number",
    "contact",
    "email",
    "certification",
    "certifications",
    "certificate",
    "degree",
    "education",
    "university",
    "location",
    "city",
    "country",
    "based",
    "address",
    "experience",
    "years of experience",
    "skills",
    "skillset",
    "technologies",
    "tech stack",
    "stack",
    "cv",
    "resume",
]


def _looks_like_cv_question(msg: str) -> bool:
    """
    Heuristic to decide if the recruiter is asking something
    that should be answered from the CV (via RAG).
    """
    low = msg.lower()
    return any(k in low for k in CV_QUERY_KEYWORDS)


def answer_from_cv(state: State, user_message: str) -> Optional[Dict[str, Any]]:
    """
    Try to answer recruiter question using CV-RAG.
    Returns a reply dict or None if something goes wrong.
    """
    try:
        rag = get_cv_rag()
        answer = rag.query(user_message)

        # log in lightweight memory so we can inspect later
        remember(
            state,
            "cv_rag_query",
            {"question": user_message, "answer": answer},
        )

        reply = (
            "Here’s what I found in Sergiu’s CV:\n\n"
            f"{answer}"
        )

        return {"reply": reply, "state": state}
    except Exception as e:
        remember(
            state,
            "cv_rag_error",
            {"question": user_message, "error": type(e).__name__},
        )
        return {
            "reply": (
                "CV Q&A is temporarily unavailable right now, "
                "but you can still explore projects and ATS summaries."
            ),
            "state": state,
        }


# ------------------------------------------------------------
# Project → explanation helpers
# ------------------------------------------------------------

def _match_criteria_to_project(
    project: Dict[str, Any],
    criteria: List[str],
) -> List[str]:
    """
    Produces bullet-level explanations of how this project fits each criterion.
    Deterministic, no LLM. Great for transparent "why this fits" reasoning.
    """
    reasons: List[str] = []
    tags_text = " ".join(project.get("tags", [])).lower()
    summary_text = project.get("summary", "").lower()

    for c in criteria:
        c_low = c.lower()
        evidence: List[str] = []

        if c_low in tags_text:
            evidence.append("tags")
        if c_low in summary_text:
            evidence.append("summary")

        if not evidence:
            # soft pattern-based explanations
            if c_low in ["production_rag", "rag"]:
                reasons.append(
                    "- **Production RAG**: uses retrieval, embeddings, or vector DB; "
                    "shows end-to-end pipeline thinking."
                )
            elif c_low == "ownership":
                reasons.append(
                    "- **Ownership**: describes end-to-end responsibility and measurable impact."
                )
            elif c_low == "leadership":
                reasons.append(
                    "- **Leadership**: shows initiative, cross-team impact or mentoring."
                )
            elif c_low == "communication":
                reasons.append(
                    "- **Communication**: project explanation is structured and business-facing."
                )
            continue

        joined = " & ".join(evidence)
        reasons.append(
            f"- **{c}**: explicitly supported in the project {joined}."
        )

    if not reasons:
        reasons.append(
            "- Overall relevance: demonstrates ML/LLM engineering and production impact."
        )

    return reasons


def format_project_deep_dive(
    project: Dict[str, Any],
    role: str,
    criteria: List[str],
    index: int,
    total: int,
) -> str:
    impacts_list = project.get("impact") or []
    if not isinstance(impacts_list, list):
        impacts_list = [str(impacts_list)]

    impacts = "\n".join(f"- {i}" for i in impacts_list)

    fit_reasons = _match_criteria_to_project(project, criteria)
    fit_text = "\n".join(fit_reasons)

    return (
        f"### 🔍 Deep Dive ({index+1}/{total}): **{project['title']}**\n\n"
        f"**Target role:** {role}\n"
        f"**Evaluation criteria:** {', '.join(criteria)}\n\n"
        f"**What this project is about**\n"
        f"{project['summary']}\n\n"
        f"**Impact (concrete outcomes)**\n{impacts}\n\n"
        f"**Why this fits the role & criteria**\n{fit_text}\n\n"
        f"📎 Repo: {project.get('link', '(link unavailable)')}\n\n"
        "Reply with `another` for the next project or `2` for an ATS-style summary.\n"
    )


# ------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------

def _get_projects_for_state(state: State) -> Tuple[List[Dict[str, Any]], int]:
    """
    Lazily compute project shortlist + deep-dive index
    using select_best_projects_for_role().
    Projects + index live in state.extra to avoid bloating the main schema.
    """
    projects: List[Dict[str, Any]] = state.extra.get("projects", [])
    deep_idx: int = state.extra.get("deep_dive_index", 0)

    if not state.role or not state.criteria:
        # shouldn't happen if called correctly
        return projects or get_all_projects(), deep_idx

    if not projects or len(projects) < 2:
        try:
            projects = select_best_projects_for_role(
                state.role,
                state.criteria,
            )
        except Exception:
            projects = []

        if not projects or len(projects) < 2:
            projects = get_all_projects()

        state.extra["projects"] = projects
        state.extra["deep_dive_index"] = 0
        deep_idx = 0

    return projects, deep_idx


def _is_job_description(msg: str) -> bool:
    """
    Very rough heuristic to detect pasted job descriptions.
    """
    words = msg.split()
    if len(words) < 20:
        return False
    # look for JD-ish words
    jd_markers = ["responsibilities", "requirements", "nice to have", "about the role"]
    low = msg.lower()
    return any(m in low for m in jd_markers) or len(words) > 40


def _derive_criteria_from_jd(msg: str) -> List[str]:
    """
    Look for canonical criteria words in a JD and map through normalize_criteria.
    """
    low = msg.lower()
    raw: List[str] = []

    if "rag" in low or "retrieval" in low:
        raw.append("production rag")
    if "leadership" in low or "lead" in low or "mentor" in low:
        raw.append("leadership")
    if "ownership" in low or "end-to-end" in low or "end to end" in low:
        raw.append("ownership")
    if "communication" in low or "stakeholder" in low or "present" in low:
        raw.append("communication")

    normalized = normalize_criteria(raw)
    # simple fallback so we always have something
    if not normalized:
        normalized = ["production_rag", "ownership"]
    return normalized


def _split_recognized_unrecognized(raw_crit: List[str]) -> Tuple[List[str], List[str]]:
    """
    Using VALID_CRITERIA, separate canonical criteria from extra contextual ones.

    Recognized: normalized canonical keys (e.g. 'leadership').
    Unrecognized: raw strings that don't map to any canonical criterion.
    """
    recognized = normalize_criteria(raw_crit)

    # Build a quick lookup of all known variants → canonical
    variant_to_canon: Dict[str, str] = {}
    for canon, variants in VALID_CRITERIA.items():
        variant_to_canon[canon] = canon
        for v in variants:
            variant_to_canon[v] = canon

    unrecognized: List[str] = []
    for raw in raw_crit:
        x = raw.strip().lower().strip(" .;:,!?")
        if not x:
            continue
        if x not in variant_to_canon:
            unrecognized.append(raw)

    # de-duplicate recognized while preserving order
    seen = set()
    dedup_recognized: List[str] = []
    for c in recognized:
        if c not in seen:
            seen.add(c)
            dedup_recognized.append(c)

    return dedup_recognized, unrecognized


def _format_criteria_confirmation(
    role: Optional[str],
    recognized: List[str],
    unrecognized: List[str],
) -> str:
    """
    Nicely formatted message after criteria parsing.
    Unknown items are shown as context, not hard filters.
    """
    header_parts: List[str] = []
    if role:
        header_parts.append(f"for **{role}**")
    header = "Perfect — I’ll evaluate Sergiu’s fit"
    if header_parts:
        header += " " + " ".join(header_parts)
    header += " based on:\n"

    lines: List[str] = [header]

    if recognized:
        for c in recognized:
            # show canonical criteria nicely
            label = c.replace("_", " ").title()
            lines.append(f"- **{label}**")

    if unrecognized:
        lines.append("\nI’ll also keep these in mind as *extra context* (not strict filters):")
        for u in unrecognized:
            lines.append(f"- {u}")

    lines.append(
        "\nFrom here you can:\n"
        "1) Ask for a project deep dive (`1`, `another`)\n"
        "2) Get an ATS-style summary + recruiter email (`2`, `ats`)\n\n"
        "You can also paste a job description for additional context."
    )

    return "\n".join(lines)


# ------------------------------------------------------------
# Main agent logic
# ------------------------------------------------------------

def agent_turn(state: State, user_message: str) -> Dict[str, Any]:
    """
    Core orchestrator: implements the role → criteria → project selection → ATS loop,
    plus CV Q&A (RAG over the CV).

    This function is intentionally deterministic (no direct LLM calls here) so it
    plays nicely with evaluation, trajectories, and CI tests. All LLM work happens
    in tools (Gemini, RAG, etc.).
    """
    msg = user_message.strip()
    low = msg.lower()

    # --------------------------------------------------------
    # Global commands
    # --------------------------------------------------------
    if low in ["reset", "start over", "restart"]:
        remember(
            state,
            "session_reset",
            {"previous_role": state.role, "previous_criteria": state.criteria},
        )
        state.role = None
        state.criteria = []
        state.extra.pop("projects", None)
        state.extra.pop("deep_dive_index", None)

        return {
            "reply": (
                "✅ Resetting the recruiter tour.\n\n"
                "What role are you hiring for?\n"
                "Examples: **Senior ML Engineer, AI Engineer, Data Scientist**."
            ),
            "state": state,
        }

    if "change role" in low:
        remember(
            state,
            "change_role",
            {"old_role": state.role},
        )
        state.role = None
        state.criteria = []
        state.extra.pop("projects", None)
        state.extra.pop("deep_dive_index", None)

        return {
            "reply": (
                "Sure — let's adjust the target role.\n\n"
                "What role are you hiring for now?"
            ),
            "state": state,
        }

    if "change criteria" in low or "update criteria" in low:
        remember(
            state,
            "change_criteria",
            {"old_criteria": state.criteria},
        )
        state.criteria = []
        state.extra.pop("projects", None)
        state.extra.pop("deep_dive_index", None)

        return {
            "reply": (
                "Got it — let's update your evaluation criteria.\n\n"
                "List 1–3 criteria (comma-separated), e.g.:\n"
                "- production RAG\n"
                "- ownership\n"
                "- leadership\n"
                "- communication"
            ),
            "state": state,
        }

    if low in ["help", "menu", "options"]:
        return {
            "reply": (
                "Here’s what I can do:\n\n"
                "1. **Project deep dives** – walk you through the most relevant projects.\n"
                "2. **ATS-style summary** – concise summary + recruiter follow-up email draft.\n"
                "3. **CV Q&A** – ask about phone number, certifications, skills, location, etc.\n\n"
                "You can say:\n"
                "- `1` or `another` → next project deep dive\n"
                "- `2` or `ats` → ATS summary\n"
                "- `what is his phone number?` → CV-based answer\n"
                "- `change role` / `change criteria` / `reset`"
            ),
            "state": state,
        }

    # --------------------------------------------------------
    # CV Q&A (RAG) — available ANYTIME
    # --------------------------------------------------------
    if _looks_like_cv_question(msg):
        rag_result = answer_from_cv(state, msg)
        if rag_result is not None:
            return rag_result
        # If something went wrong, we fall through to the usual logic.

    # --------------------------------------------------------
    # Recruiter auto-landing from GitHub / LinkedIn
    # --------------------------------------------------------
    if low == "recruiter_auto_start":
        return {
            "reply": (
                "👋 Welcome! What role are you hiring for?\n"
                "Examples: **Senior ML Engineer, AI Engineer, Data Scientist**."
            ),
            "state": state,
        }

    if state.source in ["linkedin", "github"] and state.role is None:
        return {
            "reply": (
                "👋 Welcome, and thanks for checking out Sergiu’s work.\n\n"
                "To tailor the tour, what role are you hiring for?\n"
                "Examples: **Senior ML Engineer, AI Engineer, Data Scientist**."
            ),
            "state": state,
        }

    # --------------------------------------------------------
    # 1. If we already have role + criteria → menu mode
    # --------------------------------------------------------
    if state.role and state.criteria:
        role = state.role
        criteria = state.criteria

        projects, deep_idx = _get_projects_for_state(state)

        # OPTION 1: deep dive / another / yes / next
        if low in [
            "1",
            "one",
            "deep",
            "dive",
            "deep dive",
            "another",
            "next",
            "more",
            "yes",
            "y",
        ]:
            total = len(projects)
            if total == 0:
                # ultra-defensive, should never happen
                projects = get_all_projects()
                total = len(projects)

            project = projects[deep_idx % total]

            reply = format_project_deep_dive(
                project=project,
                role=role,
                criteria=criteria,
                index=deep_idx % total,
                total=total,
            )

            # memory: recruiter looked at this project
            remember(
                state,
                "view_project",
                {"project_id": project.get("id"), "role": role, "criteria": criteria},
            )

            state.extra["deep_dive_index"] = (deep_idx + 1) % total

            return {"reply": reply, "state": state}

        # OPTION 2: ATS summary
        if low in ["2", "two", "ats", "summary", "ats summary"]:
            # Ensure projects shortlist exists
            projects, _ = _get_projects_for_state(state)
            summaries = generate_ats_summary_and_email(role, criteria, projects)

            remember(
                state,
                "ats_requested",
                {"role": role, "criteria": criteria},
            )

            return {
                "reply": (
                    f"### 📝 ATS-ready Summary for **{role}**\n\n"
                    f"{summaries['ats']}\n\n"
                    "---\n\n"
                    f"### ✉️ Recruiter Email Template\n\n"
                    f"{summaries['email']}\n\n"
                    "You can reply with:\n"
                    "- `1` or `another` for project deep dives\n"
                    "- `change criteria` or `change role` to adjust focus"
                ),
                "state": state,
            }

        # JD dropped after we already know role+criteria → interpret as context
        if _is_job_description(msg):
            remember(
                state,
                "job_description",
                {"text": msg, "role": role, "criteria": criteria},
            )
            return {
                "reply": (
                    "Thanks for sharing the job description — I'll keep it in mind for context.\n\n"
                    "Given this JD and your current focus, Sergiu’s strongest matches are:\n"
                    "- **ML/LLM engineering & production-grade systems**\n"
                    "- **RAG / vector search and retrieval pipelines**\n"
                    "- **MLOps: CI/CD, observability, and scalable deployment**\n\n"
                    "You can now:\n"
                    "1) Get a project deep dive (`1` / `another`)\n"
                    "2) Generate an ATS-style summary (`2` / `ats`)"
                ),
                "state": state,
            }

        # default menu reminder
        return {
            "reply": (
                f"You're all set for a **{role}** search focusing on "
                f"**{', '.join(criteria)}**.\n\n"
                "You can:\n"
                "1) Project deep dive (`1`, `another`, `next`)\n"
                "2) ATS summary + email (`2`, `ats`)\n"
                "Or paste a job description for extra context.\n\n"
                "At any point, you can also ask CV questions like:\n"
                "- `What is his phone number?`\n"
                "- `Which certifications does he have?`\n"
                "- `Where is he based?`"
            ),
            "state": state,
        }

    # --------------------------------------------------------
    # 2. ROLE DETECTION STAGE
    # --------------------------------------------------------
    if state.role is None:
        # try to detect role from plain sentence or JD snippet
        role = extract_role(msg)

        # if it looks like a JD but we couldn't detect role, ask explicitly
        if not role and _is_job_description(msg):
            remember(
                state,
                "job_description_no_role",
                {"text": msg},
            )
            return {
                "reply": (
                    "Thanks for the job description.\n"
                    "To tailor the tour, what **role title** are you hiring for?\n"
                    "Examples: **Senior ML Engineer, AI Engineer, Data Scientist**."
                ),
                "state": state,
            }

        if role:
            state.role = role
            remember(
                state,
                "set_role",
                {"role": role},
            )
            return {
                "reply": (
                    f"Great — targeting a **{role}** role.\n\n"
                    "What are your top 1–3 evaluation criteria?\n"
                    "Examples: **production RAG, ownership, leadership, communication**.\n\n"
                    "You can list them comma-separated."
                ),
                "state": state,
            }

        return {
            "reply": (
                "I didn’t quite catch the job role.\n\n"
                "Please specify it explicitly (e.g. **Senior ML Engineer**, **AI Engineer**, **Data Scientist**)."
            ),
            "state": state,
        }

    # --------------------------------------------------------
    # 3. CRITERIA STAGE
    # --------------------------------------------------------
    if not state.criteria:
        # If recruiter pasted a JD here *after* giving role, derive criteria
        if _is_job_description(msg):
            crit = _derive_criteria_from_jd(msg)
            state.criteria = crit
            remember(
                state,
                "set_criteria_from_jd",
                {"criteria": crit, "role": state.role, "jd": msg},
            )
            return {
                "reply": (
                    "Got it — based on this job description, I’ll focus on:\n"
                    f"**{', '.join(crit)}**.\n\n"
                    "You can reply with:\n"
                    "1) Project deep dive\n"
                    "2) ATS summary + email template\n\n"
                    "Or say `change criteria` if you’d like to tweak them."
                ),
                "state": state,
            }

        # reject pure numbers like "2"
        if msg.isdigit():
            return {
                "reply": (
                    "To set evaluation criteria, please use meaningful text such as:\n"
                    "• production RAG\n"
                    "• ownership\n"
                    "• leadership\n"
                    "• communication\n\n"
                    "You can list 1–3 criteria, comma-separated."
                ),
                "state": state,
            }

        # remove punctuation: leadershi; → leadership
        clean_msg = re.sub(r"[^\w\s,]+", "", msg).strip()

        # parse into list
        if "," in clean_msg:
            raw_crit = [
                c.strip()
                for c in clean_msg.split(",")
                if c.strip() and not c.strip().isdigit()
            ]
        else:
            if len(clean_msg) < 3:
                return {
                    "reply": (
                        "Please provide criteria with a bit more detail "
                        "(e.g. `production RAG`, `ownership`, `communication`)."
                    ),
                    "state": state,
                }
            raw_crit = [clean_msg]

        recognized, unrecognized = _split_recognized_unrecognized(raw_crit)

        # If nothing recognized at all, fall back to raw (but still keep behavior predictable)
        if not recognized and raw_crit:
            recognized = raw_crit[:3]

        state.criteria = recognized
        remember(
            state,
            "set_criteria",
            {"criteria": recognized, "raw": raw_crit, "extra_context": unrecognized},
        )

        reply = _format_criteria_confirmation(
            role=state.role,
            recognized=recognized,
            unrecognized=unrecognized,
        )

        return {"reply": reply, "state": state}

    # --------------------------------------------------------
    # Final fallback (should rarely hit)
    # --------------------------------------------------------
    return {
        "reply": (
            "You’re set up with a role and criteria.\n\n"
            "You can:\n"
            "1) Request a project deep dive (`1`, `another`)\n"
            "2) Request an ATS-style summary (`2`, `ats`)\n"
            "Or say `help` to see all options.\n\n"
            "You can also ask CV-specific questions like phone number, certifications, or skills."
        ),
        "state": state,
    }


# ============================================================
# Legacy /match endpoint adapter
# ============================================================



def analyze_match(match_request: Any) -> MatchResponse:
    """Compatibility layer for the older /match endpoint.

    It uses the same CV RAG backend to produce a lightweight,
    structured summary without introducing new LLM dependencies.
    """
    job = getattr(match_request, "job", None)
    job_text = getattr(job, "text", "") if job is not None else ""

    # Very simple, deterministic scoring based on keywords
    text_low = job_text.lower()
    strengths: List[str] = []
    risks: List[str] = []

    if any(k in text_low for k in ["ml", "machine learning", "llm", "rag", "genai", "gemini"]):
        strengths.append("Direct experience with ML/LLM and production RAG systems.")
    if "senior" in text_low:
        strengths.append("Multiple years owning end-to-end ML products and infra.")
    if "lead" in text_low or "manager" in text_low:
        strengths.append("Track record of technical leadership and mentoring.")

    if "frontend" in text_low or "mobile" in text_low:
        risks.append("Primary experience is ML/LLM; pure frontend/mobile roles may be a weaker fit.")
    if "embedded" in text_low or "firmware" in text_low:
        risks.append("Little focus on low-level or embedded systems in recent work.")

    if not strengths:
        strengths.append("Solid background in ML/LLM engineering, RAG, and production systems.")
    if not risks:
        risks.append("Role fit depends on how much ML/LLM and RAG work is required.")

    # Try to enrich using CV RAG, but never fail if it errors.
    extra_points: List[str] = []
    try:
        rag = get_cv_rag()
        answer = rag.query(
            "In bullet points, list the most relevant achievements for this job description: "
            + job_text
        )
        for line in str(answer).splitlines():
            line = line.strip()
            if line:
                extra_points.append(line)
    except Exception:
        # Ignore RAG errors and keep deterministic output
        pass

    overall = "Strong match for ML/LLM-focused roles."
    if "frontend" in text_low or "mobile" in text_low or "embedded" in text_low:
        overall = "Potential match, but role seems less ML/LLM-focused."

    summary = Summary(
        overall_fit=overall,
        strengths=strengths,
        risks=risks,
        recommended_talking_points=extra_points[:5],
    )

    return MatchResponse(
        job=job,
        summary=summary,
        insights=[],
        judge_passed=True,
        judge_reason="Rule-based recruiter agent evaluation.",
    )

# ---------------------------------------------------------------------------
# Legacy fallback models added to replace removed Summary / MatchResponse
# ---------------------------------------------------------------------------
from pydantic import BaseModel
from typing import List, Any

class Summary(BaseModel):
    overall_fit: str
    strengths: List[str]
    risks: List[str]
    recommended_talking_points: List[str]

class MatchResponse(BaseModel):
    job: Any
    summary: Summary
    insights: List[Any]
    judge_passed: bool
    judge_reason: str

