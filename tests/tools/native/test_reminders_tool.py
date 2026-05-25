"""reminders_tool: list (mocked), create, unknown action."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yuki.tools.native.reminders_tool import reminders_tool


def _fake(title: str, completed: bool = False) -> Any:
    r = MagicMock()
    r.title.return_value = title
    r.isCompleted.return_value = completed
    r.calendarItemIdentifier.return_value = "r1"
    return r


async def test_list_excludes_completed_by_default() -> None:
    store = MagicMock()
    with (
        patch("yuki.tools.native.reminders_tool._make_store", return_value=store),
        patch(
            "yuki.tools.native.reminders_tool._fetch",
            new=AsyncMock(return_value=[_fake("Buy milk")]),
        ),
    ):
        out = await reminders_tool(action="list")
    assert len(out) == 1
    assert out[0]["title"] == "Buy milk"


async def test_unknown_action_raises() -> None:
    store = MagicMock()
    with (
        patch("yuki.tools.native.reminders_tool._make_store", return_value=store),
        pytest.raises(ValueError),
    ):
        await reminders_tool(action="banana")
