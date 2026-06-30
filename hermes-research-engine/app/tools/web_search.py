"""Web search tool via DuckDuckGo (no key) with optional Tavily fallback."""
from __future__ import annotations

import os
from typing import List

import httpx
from duckduckgo_search import DDGS


def web_search(query: str, max_results: int = 5) -> List[dict]:
    """
    Returns list of {title, url, snippet} dicts.
    Falls back to Tavily if TAVILY_API_KEY is set and DDG fails.
    """
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({"title": r["title"], "url": r["href"], "snippet": r["body"]})
        if results:
            return results
    except Exception:
        pass

    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        return _tavily_search(query, max_results, tavily_key)
    return []


def _tavily_search(query: str, max_results: int, api_key: str) -> List[dict]:
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "max_results": max_results},
        timeout=15,
    )
    resp.raise_for_status()
    return [
        {"title": r["title"], "url": r["url"], "snippet": r["content"]}
        for r in resp.json().get("results", [])
    ]
