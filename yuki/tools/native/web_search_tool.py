"""web_search_tool — BYO search provider with browser fallback."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from yuki.tools.native.registry import DangerLevel, tool


async def _http_get(  # pragma: no cover
    url: str, headers: dict[str, str] | None = None
) -> Any:
    import requests

    return requests.get(url, headers=headers or {}, timeout=10)


def _fallback(query: str) -> dict[str, str]:
    return {
        "fallback_url": f"https://www.google.com/search?q={quote(query)}",
        "note": "no provider configured — open this URL in default browser",
    }


async def _brave(query: str) -> list[dict[str, str]]:
    key = os.environ.get("YUKI_BRAVE_API_KEY", "")
    if not key:
        return []
    resp = await _http_get(
        f"https://api.search.brave.com/res/v1/web/search?q={quote(query)}",
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
    )
    data = resp.json()
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("description", ""),
        }
        for r in data.get("web", {}).get("results", [])
    ]


@tool(name="web_search", danger=DangerLevel.READ_ONLY)
async def web_search_tool(query: str) -> Any:
    """Search the web via the configured provider (BYO key)."""
    provider = os.environ.get("YUKI_SEARCH_PROVIDER", "").lower()
    if provider == "brave":
        results = await _brave(query)
        return results or _fallback(query)
    return _fallback(query)
