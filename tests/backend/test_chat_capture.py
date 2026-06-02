"""/chat surfaces a capture_suggestion parsed from a <remember> tag."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yuki.backend.auth import generate_token, set_active_token
from yuki.backend.runtime import reset_runtime
from yuki.backend.server import create_app


class _FakeEvent:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    model_name = "fake"
    provider = "fake"

    async def ainvoke(self, messages, tools):  # noqa: ANN001
        return _FakeEvent("Noted! <remember>User uses Linear for tickets</remember>")


@pytest.fixture
def chat_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "YukiVault"))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path / "appsupport"))
    monkeypatch.setattr("yuki.providers.factory.make_llm", lambda *a, **k: _FakeLLM())
    reset_runtime()
    token = generate_token()
    set_active_token(token)
    c = TestClient(create_app())
    c.headers.update({"Authorization": f"Bearer {token}"})
    with c:
        yield c
    reset_runtime()


def _final_done(resp_text: str) -> dict:
    done = None
    for line in resp_text.splitlines():
        if line.startswith("data:"):
            ev = json.loads(line[len("data:"):].strip())
            if ev.get("type") == "done":
                done = ev
    assert done is not None, "no done event"
    return done


def test_capture_suggestion_parsed(chat_client: TestClient) -> None:
    r = chat_client.post("/chat", json={"message": "I use Linear for tickets"})
    assert r.status_code == 200
    done = _final_done(r.text)
    assert done["capture_suggestion"] == "User uses Linear for tickets"
    # the tag is stripped from the visible reply
    assert "<remember>" not in done["content"]
    assert done["content"].strip() == "Noted!"


def test_no_tag_means_null_suggestion(chat_client: TestClient, monkeypatch) -> None:
    class _Plain(_FakeLLM):
        async def ainvoke(self, messages, tools):  # noqa: ANN001
            return _FakeEvent("Just a normal answer.")

    monkeypatch.setattr("yuki.providers.factory.make_llm", lambda *a, **k: _Plain())
    r = chat_client.post("/chat", json={"message": "what's 2+2"})
    done = _final_done(r.text)
    assert done["capture_suggestion"] is None
    assert done["content"].strip() == "Just a normal answer."
