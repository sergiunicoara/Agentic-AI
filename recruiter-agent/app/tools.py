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
        "id": "ai-engineering-toolkit",
        "title": "AI Engineering Workflow Toolkit",
        "summary": (
            "Production-grade CI/CD quality gate for AI-assisted codebases: every git diff runs "
            "through a deterministic tool pipeline (AST analysis, test coverage, dependency audit) "
            "before any LLM judgement fires. FastAPI backend with live WebSocket streaming, "
            "React dashboard with approve-rate stats and eval regression scores, and a "
            "multi-metric LLM judge that blocks merges if quality regresses."
        ),
        "impact": [
            "Enforces deterministic tool checks before LLM evaluation — eliminates hallucinated verdicts",
            "Real-time WebSocket streams pipeline results to dashboard as each stage completes",
            "Multi-metric judge scores faithfulness, relevancy, and factuality per review",
            "Approve-rate and regression trend charts visible across all PRs in the dashboard",
            "One-command deploy: Docker Compose brings up API, judge, and React frontend",
        ],
        "tags": [
            "agents", "llm", "evaluation", "observability", "ci-cd", "websocket",
            "production", "fastapi", "react", "python", "agentic",
        ],
        "link": "https://github.com/sergiunicoara/Agentic-AI/tree/main/AIEngineering%20workflow%20toolkit",
        "source_repo": "Agentic-AI",
    },
    {
        "id": "ai-native-data-platform",
        "title": "AI-Native Data Platform",
        "summary": (
            "Production-grade RAG platform scaffold demonstrating the engineering patterns used "
            "in real AI-native systems: multi-stage retrieval, multimodal ingestion, runtime "
            "reliability contracts, DSPy-optimized NL→SQL, and a full Prometheus + Grafana "
            "observability stack."
        ),
        "impact": [
            "Multi-stage retrieval pipeline: embedding → re-rank → NL→SQL with DSPy optimisation",
            "Multimodal ingestion handles text, tables, and images in a unified pipeline",
            "Runtime reliability contracts (SLOs) enforce retrieval quality at inference time",
            "Prometheus + Grafana observability stack: latency, recall, and error-rate dashboards",
            "Modular scaffold: swap vector store, LLM, or retriever without changing the pipeline contract",
        ],
        "tags": [
            "rag", "production_rag", "retrieval", "embeddings", "observability",
            "multimodal", "nlp", "production", "pipeline", "llm", "python",
        ],
        "link": "https://github.com/sergiunicoara/Agentic-AI/tree/main/ai-native-data-platform",
        "source_repo": "Agentic-AI",
    },
    {
        "id": "recruiter-agent:voice-pipeline",
        "title": "Production Voice AI Pipeline",
        "summary": (
            "Real-time voice agent on Cloud Run: Deepgram nova-2 STT over WebSocket → "
            "deterministic agentic orchestrator → Google Neural2-D TTS with sentence-level "
            "streaming. Continuous conversation loop with barge-in (RMS VAD), silence keepalive, "
            "and SQLite session state. OTel-traced, critic agent (A2A), LLM-as-Judge evaluation "
            "harness, MCP tool endpoints, and CI golden dataset tests. ~600ms time-to-first-audio."
        ),
        "impact": [
            "Sub-200ms agent latency end-to-end on Cloud Run",
            "Barge-in via RMS VAD — user interrupts TTS mid-sentence instantly",
            "Silence keepalive prevents Deepgram timeout during TTS playback",
            "OTel span per voice turn: transcript len, reply len, session_id",
            "Critic agent scores every reply on faithfulness, relevancy, factuality",
            "MCP tool endpoints enable agent-to-agent discovery and validation",
        ],
        "tags": [
            "voice", "stt", "tts", "deepgram", "websocket", "agentic", "production",
            "cloud-run", "low-latency", "low_latency", "streaming", "real-time",
            "observability", "rag", "voice_ai", "python",
        ],
        "link": "https://github.com/sergiunicoara/Agentic-AI/tree/main/recruiter-agent",
        "source_repo": "Agentic-AI",
    },
    {
        "id": "agent-observability:otel-dashboard",
        "title": "Agent Observability Dashboard (OTel + gRPC)",
        "summary": (
            "Full-stack observability platform for agentic workflows: FastAPI + gRPC backend, "
            "React/Recharts frontend, OTel Collector, Postgres audit log, Redis JWT revocation. "
            "Real-time event streaming via gRPC-Web → Envoy. RBAC, AuditLogMiddleware, "
            "and an SDK with AgentTracer context manager for any agentic span."
        ),
        "impact": [
            "Production-grade OTel instrumentation with OTLP export to collector",
            "Real-time dashboard streams latency metrics per agent turn",
            "SDK: AgentTracer wraps any agentic span — zero boilerplate for consumers",
            "Docker Compose one-command: collector + backend + frontend + Postgres + Redis",
            "RBAC (viewer/developer/admin) with JWT + Redis revocation",
        ],
        "tags": [
            "observability", "otel", "opentelemetry", "langsmith", "langfuse", "grpc",
            "real-time", "streaming", "production", "agents", "monitoring", "tracing",
            "evaluation", "fastapi", "python",
        ],
        "link": "https://github.com/sergiunicoara/Agentic-AI/tree/main/agent-observability",
        "source_repo": "Agentic-AI",
    },
    {
        "id": "graphrag:ragas-pipeline",
        "title": "GraphRAG Pipeline with RAGAS Evaluation",
        "summary": (
            "Production RAG pipeline with graph-augmented retrieval: embeddings, vector store, "
            "re-ranking, and a RAGAS evaluation harness. Achieves context_precision=1.0 and "
            "context_recall=1.0 on the golden test set. Automated CI gate blocks deploys if "
            "recall drops below threshold."
        ),
        "impact": [
            "context_precision = 1.0, context_recall = 1.0 on eval dataset",
            "Automated RAGAS CI gate: no deploy if recall regresses",
            "Graph-augmented retrieval outperforms naive cosine on multi-hop queries",
            "End-to-end: ingestion → chunking → embedding → retrieval → ranking → LLM response",
        ],
        "tags": [
            "rag", "production_rag", "retrieval", "embeddings", "ranking", "evaluation",
            "ragas", "production", "pipeline", "llm", "graphrag", "vector search",
        ],
        "link": "https://github.com/sergiunicoara/Agentic-AI",
        "source_repo": "Agentic-AI",
    },
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
        "link": "https://github.com/sergiunicoara/Generative-AI",
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
        "link": "https://github.com/sergiunicoara/Agentic-AI",
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
        "link": "https://github.com/sergiunicoara/Natural-language-processing-NLP",
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
        "link": "https://github.com/sergiunicoara/DeepLearning",
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
        "link": "https://github.com/sergiunicoara",
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
        f"- Portfolio hosted on GitHub under the user 'sergiunicoara', with projects "
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
        f"All projects are available on GitHub under the username 'sergiunicoara'.\n\n"
        f"I recommend moving him forward to the next interview stage.\n\n"
        f"Best,\n"
        f"Your AI recruiter agent"
    )

    return {
        "ats": ats_text,
        "email": email_text,
    }
