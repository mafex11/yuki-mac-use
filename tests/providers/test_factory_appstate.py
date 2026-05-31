"""Factory resolves provider/model/key from app_state.json + Keychain."""

import pytest

from yuki.providers import factory


def test_resolve_reads_appstate(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    monkeypatch.delenv("YUKI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("YUKI_LLM_MODEL", raising=False)
    (tmp_path / "app_state.json").write_text(
        '{"llm_provider": "google", "llm_model": "gemini-2.5-flash"}'
    )
    provider, model = factory._resolve(None, None)
    assert provider == "google"
    assert model == "gemini-2.5-flash"


def test_env_still_overrides_appstate(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    monkeypatch.setenv("YUKI_LLM_PROVIDER", "ollama")
    (tmp_path / "app_state.json").write_text('{"llm_provider": "google"}')
    provider, _ = factory._resolve(None, None)
    assert provider == "ollama"
