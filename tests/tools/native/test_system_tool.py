"""system_tool: set_volume, toggle_dark_mode, unknown."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.system_tool import system_tool


async def test_set_volume_runs_osa() -> None:
    fake = AsyncMock(return_value="ok")
    with patch("yuki.tools.native.system_tool.osa", new=fake):
        out = await system_tool(action="set_volume", value=50)
    assert out == {"ok": True}
    fake.assert_awaited()


async def test_toggle_dark_mode() -> None:
    fake = AsyncMock(return_value="")
    with patch("yuki.tools.native.system_tool.osa", new=fake):
        out = await system_tool(action="toggle_dark_mode")
    assert out == {"ok": True}


async def test_unknown_action_raises() -> None:
    with pytest.raises(ValueError):
        await system_tool(action="banana")
