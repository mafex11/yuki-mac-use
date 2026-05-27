"""Chat router: pure /chat (fast LLM round-trip) + /chat/control (desktop loop)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_chat_rejects_empty_message(client: TestClient) -> None:
    r = client.post("/chat", json={"message": ""})
    assert r.status_code == 400


def test_chat_streams_done_event(client: TestClient) -> None:
    """Pure /chat path mocks the LLM and confirms a done event lands."""

    async def fake_stream(
        message: str, conversation_id: str | None
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "done", "content": "hi back"}

    with patch("yuki.backend.routers.chat._stream_chat", new=fake_stream), client.stream(
        "POST", "/chat", json={"message": "hi"}
    ) as r:
        assert r.status_code == 200
        body = "".join(line for line in r.iter_text())
    assert "hi back" in body
    assert "done" in body


def test_chat_control_uses_desktop_loop(client: TestClient) -> None:
    async def fake_stream(
        message: str, conversation_id: str | None
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "done", "content": "opened Notes"}

    with patch("yuki.backend.routers.chat._stream_control", new=fake_stream), client.stream(
        "POST", "/chat/control", json={"message": "open Notes"}
    ) as r:
        assert r.status_code == 200
        body = "".join(line for line in r.iter_text())
    assert "opened Notes" in body


def test_chat_control_rejects_empty(client: TestClient) -> None:
    r = client.post("/chat/control", json={"message": "  "})
    assert r.status_code == 400
