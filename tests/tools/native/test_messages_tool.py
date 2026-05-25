"""messages_tool: experimental flag, send, unknown."""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native import messages_tool as messages_mod
from yuki.tools.native.messages_tool import messages_tool
from yuki.tools.native.registry import REGISTRY


def test_messages_is_experimental() -> None:
    importlib.reload(messages_mod)
    assert REGISTRY["messages"].experimental is True


async def test_send_runs_osa() -> None:
    fake = AsyncMock(return_value="")
    with patch("yuki.tools.native.messages_tool.osa", new=fake):
        out = await messages_tool(action="send_to", recipient="+15551212", body="hi")
    assert out == {"sent": True}


async def test_unknown_raises() -> None:
    with pytest.raises(ValueError):
        await messages_tool(action="zzz")
