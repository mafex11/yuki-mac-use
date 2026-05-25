"""contacts_tool: search via mocked CNContactStore, unavailable case."""

from __future__ import annotations

from unittest.mock import patch

from yuki.tools.native.contacts_tool import contacts_tool


async def test_no_contacts_lib_returns_error() -> None:
    with patch("yuki.tools.native.contacts_tool._make_store", return_value=None):
        out = await contacts_tool(query="x")
    assert out == {"error": "Contacts unavailable"}
