from __future__ import annotations

import os
from typing import Any

import requests

TAVILY_URL = "https://api.tavily.com/search"


def tavily_search(query: str, *, max_results: int | None = None) -> list[dict[str, str]]:
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []
    limit = max_results or int(os.environ.get("SEARCH_MAX_RESULTS", "5"))
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": os.environ.get("TAVILY_SEARCH_DEPTH", "basic"),
        "max_results": limit,
    }
    resp = requests.post(TAVILY_URL, json=payload, timeout=60)
    resp.raise_for_status()
    return [
        {
            "title": str(item.get("title") or ""),
            "url": str(item.get("url") or ""),
            "snippet": str(item.get("content") or ""),
        }
        for item in resp.json().get("results", [])
    ]


def search_queries(queries: list[str]) -> list[dict[str, Any]]:
    max_queries = int(os.environ.get("SEARCH_MAX_QUERIES", "4"))
    evidence: list[dict[str, Any]] = []
    for query in queries[:max_queries]:
        query = query.strip()
        if not query:
            continue
        try:
            results = tavily_search(query)
            evidence.append({"query": query, "results": results, "error": ""})
        except requests.RequestException as exc:
            evidence.append({"query": query, "results": [], "error": str(exc)})
    return evidence
