"""Chat REPL: URL resolution, SSE parsing, post round-trip via mocked httpx."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from yuki.backend.chat_cli import _post_chat, _resolve_url


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "YUKI_BACKEND_URL",
        "YUKI_PORT",
        "YUKI_AUTH_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)


def test_resolve_url_default() -> None:
    assert _resolve_url() == "http://127.0.0.1:8765"


def test_resolve_url_uses_yuki_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_PORT", "9000")
    assert _resolve_url() == "http://127.0.0.1:9000"


def test_resolve_url_uses_explicit_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_BACKEND_URL", "http://elsewhere:1234/")
    assert _resolve_url() == "http://elsewhere:1234"


def _fake_sse_lines(payload: dict[str, Any]) -> list[str]:
    import json

    return [
        ": ping - keepalive",
        "",
        "event: done",
        f"data: {json.dumps(payload)}",
        "",
    ]


def test_post_chat_extracts_done_content() -> None:
    payload = {"type": "done", "content": "the answer is 4"}

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.iter_lines.return_value = iter(_fake_sse_lines(payload))

    fake_stream = MagicMock()
    fake_stream.__enter__ = MagicMock(return_value=fake_resp)
    fake_stream.__exit__ = MagicMock(return_value=False)

    fake_client = MagicMock()
    fake_client.stream.return_value = fake_stream

    content, _badge = _post_chat(
        fake_client, "http://x", "tok", "hi", control=False
    )
    assert content == "the answer is 4"
    # Verify it hit /chat (not /chat/control)
    args, _ = fake_client.stream.call_args
    assert args[1].endswith("/chat")


def test_post_chat_control_uses_control_path() -> None:
    payload = {"type": "done", "content": "opened"}
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.iter_lines.return_value = iter(_fake_sse_lines(payload))
    fake_stream = MagicMock()
    fake_stream.__enter__ = MagicMock(return_value=fake_resp)
    fake_stream.__exit__ = MagicMock(return_value=False)
    fake_client = MagicMock()
    fake_client.stream.return_value = fake_stream

    content, _ = _post_chat(
        fake_client, "http://x", "tok", "open notes", control=True
    )
    assert content == "opened"
    args, _ = fake_client.stream.call_args
    assert args[1].endswith("/chat/control")


def test_post_chat_propagates_error_event() -> None:
    payload = {"type": "error", "content": "boom"}
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.iter_lines.return_value = iter(_fake_sse_lines(payload))
    fake_stream = MagicMock()
    fake_stream.__enter__ = MagicMock(return_value=fake_resp)
    fake_stream.__exit__ = MagicMock(return_value=False)
    fake_client = MagicMock()
    fake_client.stream.return_value = fake_stream

    content, _ = _post_chat(
        fake_client, "http://x", "tok", "hi", control=False
    )
    assert "boom" in content


def test_post_chat_non_200_returns_error_string() -> None:
    fake_resp = MagicMock()
    fake_resp.status_code = 500
    fake_resp.read.return_value = b"server died"
    fake_stream = MagicMock()
    fake_stream.__enter__ = MagicMock(return_value=fake_resp)
    fake_stream.__exit__ = MagicMock(return_value=False)
    fake_client = MagicMock()
    fake_client.stream.return_value = fake_stream

    content, _ = _post_chat(
        fake_client, "http://x", "tok", "hi", control=False
    )
    assert "500" in content
    assert "server died" in content
