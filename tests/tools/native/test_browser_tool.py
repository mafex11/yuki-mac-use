"""browser_tool: current_url, open_url, unknown."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.browser_tool import browser_tool


async def test_current_url_returns_string() -> None:
    with patch(
        "yuki.tools.native.browser_tool.osa",
        new=AsyncMock(return_value="https://example.com"),
    ):
        out = await browser_tool(action="current_url")
    assert out == "https://example.com"


async def test_open_url_runs_osa() -> None:
    fake = AsyncMock(return_value="")
    with patch("yuki.tools.native.browser_tool.osa", new=fake):
        out = await browser_tool(action="open_url", url="https://example.com")
    assert out == {"opened": True}
    fake.assert_awaited()


async def test_unknown_action_raises() -> None:
    with pytest.raises(ValueError):
        await browser_tool(action="banana")
