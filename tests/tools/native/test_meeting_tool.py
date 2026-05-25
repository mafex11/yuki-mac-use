"""meeting_tool: experimental flag, current detection, unknown."""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native import meeting_tool as meeting_mod
from yuki.tools.native.meeting_tool import meeting_tool
from yuki.tools.native.registry import REGISTRY


def test_meeting_is_experimental() -> None:
    importlib.reload(meeting_mod)
    assert REGISTRY["meeting"].experimental is True


async def test_current_returns_app_when_running() -> None:
    with patch(
        "yuki.tools.native.meeting_tool._frontmost",
        new=AsyncMock(return_value="zoom.us"),
    ):
        out = await meeting_tool(action="current")
    assert out["app"] == "zoom.us"
    assert out["in_meeting"] is True


async def test_current_returns_none_when_no_meeting_app() -> None:
    with patch(
        "yuki.tools.native.meeting_tool._frontmost",
        new=AsyncMock(return_value="Safari"),
    ):
        out = await meeting_tool(action="current")
    assert out["in_meeting"] is False


async def test_unknown_raises() -> None:
    with patch(
        "yuki.tools.native.meeting_tool._frontmost",
        new=AsyncMock(return_value="Safari"),
    ), pytest.raises(ValueError):
        await meeting_tool(action="zzz")
