# app/tools.py

from __future__ import annotations

from typing import List, Dict, Any, Optional
import logging
import os
import time

from .github_portfolio import load_github_projects

logger = logging.getLogger(__name__)


# ============================================================
# STATIC FALLBACK PROJECTS (all real repos, used if GitHub fails)
# ============================================================

STATIC_PROJECTS: List[Dict[str, Any]] = [
    {
        "id": "Generative-AI:portfolio",
        "title": "End-to-End Generative AI Portfolio",
        "summary": (
            "Curated collection of generative AI projects in the Generative-AI repo, "
            "including RAG chatbots, vision + language apps, and API-integrated assistants."
        ),
        "impact": [
            "Demonstrates hands-on experience with multiple GenAI use cases",
            "Shows ability to structure a project portfolio clearly for recruiters",
            "Covers prompt engineering, evaluation, and practical deployment patterns",
        ],
        "tags": ["llm", "rag", "genai", "portfolio"],
        "link": "https://github.com/sergiu123456789/Generative-AI",
        "source_repo": "Generative-AI",
    },
    {
        "id": "Agentic-AI:systems",
        "title": "Agentic AI Systems",
        "summary": (
            "Experiments with agentic workflows, tools, and multi-step reasoning "
            "for building more autonomous AI systems."
        ),
        "impact": [
            "Shows understanding of modern agent patterns beyond single prompts",
            "Highlights tool-use, planning, and orchestration skills",
            "Aligns directly with 'agentic AI' course and recruiter agent project",
        ],
        "tags": ["agents", "llm", "tools", "orchestration"],
        "link": "https://github.com/sergiu123456789/Agentic-AI",
        "source_repo": "Agentic-AI",
    },
    {
        "id": "NLP:core",
        "title": "Natural Language Processing Pipelines",
        "summary": (
            "Collection of NLP projects in the Natural-language-processing-NLP repo, "
            "including classic text preprocessing, feature engineering, and modeling."
        ),
        "impact": [
            "Proves strong foundations in NLP beyond LLMs",
            "Shows comfort with tokenization, embeddings, and evaluation",
            "Useful to signal depth for roles that mix classic NLP with LLM work",
        ],
        "tags": ["nlp", "ml", "text"],
        "link": "https://github.com/sergiu123456789/Natural-language-processing-NLP",
        "source_repo": "Natural-language-processing-NLP",
    },
    {
        "id": "DeepLearning:experiments",
        "title": "Deep Learning Experiments",
        "summary": (
            "DeepLearning repo with neural network experiments, training loops, "
            "and model architectures."
        ),
        "impact": [
            "Shows ability to work with deep learning frameworks end-to-end",
            "Demonstrates experimentation mindset (trying architectures, tuning)",
            "Good signal for roles that care about DL fundamentals",
        ],
        "tags": ["deep-learning", "pytorch", "ml"],
        "link": "https://github.com/sergiu123456789/DeepLearning",
        "source_repo": "DeepLearning",
    },
    {
        "id": "ML-core:classic",
        "title": "Classic ML: Regression, Clustering & Dimensionality Reduction",
        "summary": (
            "Regression, Clustering, and Dimensionality-reduction repos combined: "
            "implementing fundamental ML techniques and visualizing results."
        ),
        "impact": [
            "Shows solid understanding of core ML algorithms",
            "Demonstrates ability to explain and visualize results",
            "Useful to prove fundamentals for ML Engineer roles",
        ],
        "tags": ["ml", "regression", "clustering", "dimensionality-reduction"],
        "link": "https://github.com/sergiu123456789",
        "source_repo": "multiple",
    },
]


# ============================================================
# GITHUB-BACKED PROJECT LOADING + TTL CACHE
# ============================================================

_CACHE: Optional[Dict[str, Any]] = None
_CACHE_TTL_SECONDS = int(os.getenv("PORTFOLIO_TTL_SECONDS", "21600"))  # 6h


def _is_cache_valid() -> bool:
    if not _CACHE:
        return False
    ts = _CACHE.get("timestamp", 0)
    return (time.time() - ts) < _CACHE_TTL_SECONDS


def _set_cache(projects: List[Dict[str, Any]]) -> None:
    global _CACHE
    _CACHE = {"timestamp": time.time(), "projects": projects}


def _merge_with_static_projects(
    dynamic_projects: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Ensure static projects are available as fallback + extra signals,
    without duplicating IDs.
    """
    if not dynamic_projects:
        return STATIC_PROJECTS

    dynamic_ids = {p.get("id") for p in dynamic_projects}
    merged = list(dynamic_projects)

    for sp in STATIC_PROJECTS:
        if sp.get("id") not in dynamic_ids:
            merged.append(sp)

    return merged


def get_all_projects() -> List[Dict[str, Any]]:
    """
    Main access point for the agent:
    - Uses cached GitHub-backed projects if fresh
    - On miss/expiry: reloads from GitHub
    - Always returns *something* (falls back to STATIC_PROJECTS)
    """
    global _CACHE

    if _is_cache_valid():
        return _CACHE["projects"]

    try:
        gh_projects = load_github_projects()
        projects = _merge_with_static_projects(gh_projects)
        if not projects:
            logger.warning("GitHub returned no projects, using static fallback.")
            projects = STATIC_PROJECTS
    except Exception as e:
        logger.warning("GitHub project loading failed, using static fallback: %s", e)
        projects = STATIC_PROJECTS

    _set_cache(projects)
    return projects


def force_refresh_portfolio() -> int:
    """
    Explicit refresh, used by /admin/refresh-portfolio.
    Returns the number of projects now in cache.
    """
    try:
        gh_projects = load_github_projects()
        projects = _merge_with_static_projects(gh_projects)
        if not projects:
            projects = STATIC_PROJECTS
    except Exception as e:
        logger.warning("Force-refresh failed, using static projects: %s", e)
        projects = STATIC_PROJECTS

    _set_cache(projects)
    return len(projects)


# ============================================================
# SCORING LOGIC
# ============================================================

def score_project_for_role_and_criteria(
    project: Dict[str, Any],
    role: str,
    criteria: List[str],
) -> int:
    """
    Simple heuristic scoring:
    - +5 if a criterion word appears in tags or summary
    - +4 if the role keyword appears in title/summary
    - +2 if any token from role appears in tags or summary
    """
    score = 0
    crit_text = " ".join(criteria).lower()
    proj_text = (
        f"{project.get('title','')} "
        f"{project.get('summary','')} "
        f"{' '.join(project.get('tags', []))}"
    ).lower()
    title_text = project.get("title", "").lower()

    # Match criteria words
    for token in crit_text.split():
        if token and token in proj_text:
            score += 5

    # Match complete role phrase roughly
    if role and role.lower() in proj_text:
        score += 4

    # Match role tokens
    for token in role.lower().split():
        if token and token in title_text:
            score += 4
        elif token and token in proj_text:
            score += 2

    return score


# ============================================================
# SELECT BEST PROJECTS
# ============================================================

def select_best_projects_for_role(role: str, criteria: List[str]) -> List[Dict[str, Any]]:
    """
    Returns the top 2–3 relevant projects (full dicts) based on scoring.
    Grounded in real GitHub repos where possible.
    """
    projects = get_all_projects()
    scored = []

    for p in projects:
        relevance = score_project_for_role_and_criteria(p, role, criteria)
        scored.append((relevance, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [p for score, p in scored if score > 0][:3]

    # If everything scored 0 (rare), just take 3 by default
    if not top:
        top = [p for _, p in scored[:3]]

    return top


# ============================================================
# ATS SUMMARY + RECRUITER EMAIL
# ============================================================

def generate_ats_summary_and_email(
    role: str,
    criteria: List[str],
    projects: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Generates:
      - ATS-style summary text
      - Recruiter follow-up email draft
    using grounded project information.
    """
    crit_text = ", ".join(criteria) if criteria else "the key requirements"

    proj_lines = []
    for p in projects:
        proj_lines.append(f"- {p.get('title','(untitled)')} → {p.get('summary','')}")

    projects_list_text = "\n".join(proj_lines) if proj_lines else "Projects list not available."

    ats_text = (
        f"Role: {role}\n"
        f"Key criteria: {crit_text}\n\n"
        f"Candidate: Sergiu\n\n"
        f"Summary:\n"
        f"- Strong hands-on experience across ML and Generative AI projects.\n"
        f"- Portfolio hosted on GitHub under the user 'sergiu123456789', with projects "
        f"covering agents, RAG, NLP, and classic ML.\n"
        f"- Relevant projects:\n"
        f"{projects_list_text}\n"
    )

    email_text = (
        f"Hi,\n\n"
        f"I reviewed Sergiu's profile for the {role} opening.\n\n"
        f"He shows strong alignment with the role, especially in: {crit_text}.\n\n"
        f"Some relevant projects:\n"
        f"{projects_list_text}\n\n"
        f"All projects are available on GitHub under the username 'sergiu123456789'.\n\n"
        f"I recommend moving him forward to the next interview stage.\n\n"
        f"Best,\n"
        f"Your AI recruiter agent"
    )

    return {
        "ats": ats_text,
        "email": email_text,
    }
