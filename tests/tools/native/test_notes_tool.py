"""notes_tool: list/create/read/delete via mocked osa."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.notes_tool import notes_tool


async def test_list_returns_titles() -> None:
    with patch(
        "yuki.tools.native.notes_tool.osa", new=AsyncMock(return_value="A\nB\nC")
    ):
        out = await notes_tool(action="list")
    assert out == ["A", "B", "C"]


async def test_create_calls_osa_with_payload() -> None:
    fake = AsyncMock(return_value="ok")
    with patch("yuki.tools.native.notes_tool.osa", new=fake):
        out = await notes_tool(action="create", title="t", body="hello")
    assert out == {"created": True}
    fake.assert_awaited()


async def test_read_returns_body() -> None:
    with patch(
        "yuki.tools.native.notes_tool.osa", new=AsyncMock(return_value="body text")
    ):
        out = await notes_tool(action="read", title="t")
    assert out == "body text"


async def test_unknown_action_raises() -> None:
    with pytest.raises(ValueError):
        await notes_tool(action="banana")
