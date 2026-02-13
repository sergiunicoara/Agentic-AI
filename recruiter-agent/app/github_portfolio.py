# app/github_portfolio.py

from __future__ import annotations

from typing import List, Dict, Any, Optional
import base64
import logging
import os

import requests

logger = logging.getLogger(__name__)

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "sergiu123456789")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # optional, for higher rate limits

GITHUB_API_BASE = "https://api.github.com"


# ------------------------------------------------------------
# Low-level GitHub helpers
# ------------------------------------------------------------

def _github_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{GITHUB_API_BASE}{path}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _fetch_repos() -> List[Dict[str, Any]]:
    """List all repos for the configured user."""
    repos = _github_get(f"/users/{GITHUB_USERNAME}/repos", params={"per_page": 100})
    if not isinstance(repos, list):
        return []
    return repos


def _fetch_markdown_files(owner: str, repo: str) -> List[Dict[str, Any]]:
    """
    Fetch top-level markdown files from a repo using the Contents API.
    We only look at root level to keep things cheap.
    """
    try:
        contents = _github_get(f"/repos/{owner}/{repo}/contents")
    except requests.HTTPError as e:
        logger.debug("No contents for repo %s: %s", repo, e)
        return []

    if not isinstance(contents, list):
        return []

    md_files: List[Dict[str, Any]] = []
    for item in contents:
        if item.get("type") == "file":
            name = (item.get("name") or "").lower()
            if name.endswith(".md"):
                md_files.append(item)

    return md_files


def _download_file(owner: str, repo: str, path: str) -> str:
    """
    Download a file via the Contents API and return decoded text.
    """
    data = _github_get(f"/repos/{owner}/{repo}/contents/{path}")
    # Standard contents API: base64-encoded "content"
    content = data.get("content")
    encoding = data.get("encoding")

    if content and encoding == "base64":
        try:
            return base64.b64decode(content).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    # Fallback: if GitHub ever returns raw text
    if isinstance(data, str):
        return data

    return ""


# ------------------------------------------------------------
# Markdown → project parsing
# ------------------------------------------------------------

def _parse_markdown_to_project(
    owner: str,
    repo: str,
    md_name: str,
    md_text: str,
    default_branch: str,
) -> Dict[str, Any]:
    """
    Turn a Markdown file into a structured "project" dict used by the agent.
    Heuristics only, no LLM.
    """
    lines = md_text.splitlines()

    # --- Title: first H1 (#) or fallback to repo + filename ---
    title: Optional[str] = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            break

    if not title:
        base_name, _ = os.path.splitext(md_name)
        title = f"{repo} – {base_name}"

    # --- Summary: lines after title, until blank/section/bullets ---
    summary_lines: List[str] = []
    seen_title = False

    for line in lines:
        if not seen_title:
            if line.strip().startswith("#"):
                seen_title = True
            continue

        stripped = line.strip()
        if not stripped:
            if summary_lines:
                break
            continue

        # new section
        if stripped.startswith("##"):
            if summary_lines:
                break
            else:
                continue

        # stop summary on first bullet if we already collected something
        if stripped.startswith(("-", "*")) and summary_lines:
            break

        # otherwise treat as summary text
        summary_lines.append(stripped)

    summary = " ".join(summary_lines).strip()
    if not summary:
        summary = f"Project in repo `{repo}` from file `{md_name}`."

    # --- Impacts: all bullet lines (trimmed) ---
    impacts: List[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith(("-", "*")) and len(s) > 2:
            impacts.append(s.lstrip("-* ").strip())
    impacts = impacts[:6]  # keep it compact

    # --- Tags: simple keyword search ---
    text_lower = md_text.lower()
    tags: List[str] = []

    def _tag_if(keyword: str, tag: str) -> None:
        if keyword in text_lower and tag not in tags:
            tags.append(tag)

    _tag_if("rag", "rag")
    _tag_if("retrieval", "rag")
    _tag_if("agent", "agents")
    _tag_if("autogen", "agents")
    _tag_if("crewai", "agents")
    _tag_if("langchain", "langchain")
    _tag_if("langgraph", "langgraph")
    _tag_if("llm", "llm")
    _tag_if("pytorch", "pytorch")
    _tag_if("tensorflow", "tensorflow")
    _tag_if("nlp", "nlp")
    _tag_if("transformer", "transformers")
    _tag_if("cv", "cv")
    _tag_if("vision", "vision")
    _tag_if("docker", "docker")
    _tag_if("kubernetes", "kubernetes")
    _tag_if("gcp", "gcp")
    _tag_if("aws", "aws")
    _tag_if("azure", "azure")

    if not tags:
        tags.append("ml")

    link = f"https://github.com/{owner}/{repo}/blob/{default_branch}/{md_name}"

    return {
        "id": f"{repo}:{md_name}",
        "title": title,
        "summary": summary,
        "impact": impacts,
        "tags": tags,
        "link": link,
        "source_repo": repo,
    }


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def load_github_projects() -> List[Dict[str, Any]]:
    """
    Load *all* projects from ALL repos for the configured GitHub user.
    - Every top-level .md file becomes a "project"
    - Uses README.md plus any extra markdown files (like AutoGen.md, CrewAI.md, etc.)
    """
    logger.info("Loading GitHub portfolio for user %s", GITHUB_USERNAME)
    projects: List[Dict[str, Any]] = []

    try:
        repos = _fetch_repos()
    except Exception as e:
        logger.warning("Failed to fetch GitHub repos for %s: %s", GITHUB_USERNAME, e)
        return projects

    for repo_info in repos:
        repo_name = repo_info.get("name")
        if not repo_name:
            continue

        # Skip archived repos to reduce noise
        if repo_info.get("archived"):
            continue

        owner_login = repo_info.get("owner", {}).get("login") or GITHUB_USERNAME
        default_branch = repo_info.get("default_branch") or "main"

        try:
            md_files = _fetch_markdown_files(owner_login, repo_name)
        except Exception as e:
            logger.debug("Skipping repo %s: cannot list contents (%s)", repo_name, e)
            continue

        for f in md_files:
            path = f.get("path") or f.get("name")
            if not path:
                continue
            name = f.get("name") or path

            try:
                text = _download_file(owner_login, repo_name, path)
            except Exception as e:
                logger.debug("Failed to download %s/%s: %s", repo_name, path, e)
                continue

            if not text.strip():
                continue

            project = _parse_markdown_to_project(
                owner=owner_login,
                repo=repo_name,
                md_name=name,
                md_text=text,
                default_branch=default_branch,
            )
            projects.append(project)

    logger.info("Loaded %d projects from GitHub", len(projects))
    return projects
