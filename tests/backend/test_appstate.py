import json
from pathlib import Path
import pytest
from yuki.backend import appstate


def test_returns_defaults_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    cfg = appstate.load()
    assert cfg["llm_provider"] == "google"
    assert cfg["llm_model"] == "gemini-2.5-flash"


def test_reads_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    (tmp_path / "app_state.json").write_text(
        json.dumps({"llm_provider": "anthropic", "llm_model": "claude-sonnet-4-6"})
    )
    cfg = appstate.load()
    assert cfg["llm_provider"] == "anthropic"
    assert cfg["llm_model"] == "claude-sonnet-4-6"


def test_api_key_from_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    monkeypatch.setenv("GOOGLE_API_KEY", "env-key-123")
    assert appstate.api_key_for("google") == "env-key-123"


def test_api_key_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(appstate, "_keychain_get", lambda account: None)
    assert appstate.api_key_for("google") is None
