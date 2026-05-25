"""mail_tool: list_unread, send, unknown."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.mail_tool import mail_tool


async def test_list_unread_returns_messages() -> None:
    out_text = "Sarah | Re: Q3 plan\nBob | Quick q"
    with patch("yuki.tools.native.mail_tool.osa", new=AsyncMock(return_value=out_text)):
        out = await mail_tool(action="list_unread", limit=10)
    assert len(out) == 2
    assert out[0]["sender"] == "Sarah"


async def test_send_calls_osa() -> None:
    fake = AsyncMock(return_value="ok")
    with patch("yuki.tools.native.mail_tool.osa", new=fake):
        out = await mail_tool(action="send", to="x@y.com", subject="Hi", body="hello")
    assert out == {"sent": True}
    fake.assert_awaited()


async def test_unknown_action_raises() -> None:
    with pytest.raises(ValueError):
        await mail_tool(action="banana")
