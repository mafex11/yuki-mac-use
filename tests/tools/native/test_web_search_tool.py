"""web_search_tool: brave provider, fallback when none configured."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yuki.tools.native.web_search_tool import web_search_tool


async def test_brave_returns_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_SEARCH_PROVIDER", "brave")
    monkeypatch.setenv("YUKI_BRAVE_API_KEY", "k")
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = {
        "web": {
            "results": [{"title": "T", "url": "https://x", "description": "d"}]
        }
    }
    with patch(
        "yuki.tools.native.web_search_tool._http_get",
        new=AsyncMock(return_value=fake_resp),
    ):
        out = await web_search_tool(query="hello")
    assert len(out) == 1
    assert out[0]["title"] == "T"


async def test_no_provider_returns_fallback_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("YUKI_SEARCH_PROVIDER", raising=False)
    out = await web_search_tool(query="hello world")
    assert "fallback_url" in out
