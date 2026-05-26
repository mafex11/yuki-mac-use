"""Provider factory: env > settings > defaults; clear errors on misconfig."""

from __future__ import annotations

from pathlib import Path

import pytest

from yuki.providers.factory import (
    ProviderConfigError,
    is_tool_call_unreliable,
    make_llm,
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin index dir so settings.json doesn't leak between tests."""
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.delenv("YUKI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("YUKI_LLM_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_default_provider_is_anthropic_and_errors_without_key() -> None:
    with pytest.raises(ProviderConfigError) as exc:
        make_llm()
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_anthropic_with_key_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    llm = make_llm()
    assert llm.provider == "anthropic"
    assert llm.model_name == "claude-sonnet-4-6"


def test_env_override_to_ollama() -> None:
    llm = make_llm(provider="ollama")
    assert llm.provider == "ollama"
    assert llm.model_name == "qwen3-vl:8b"


def test_env_override_to_ollama_with_model() -> None:
    llm = make_llm(provider="ollama", model="devstral-small-2:24b")
    assert llm.model_name == "devstral-small-2:24b"


def test_env_var_overrides_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("YUKI_LLM_MODEL", "deepseek-r1:1.5b")
    llm = make_llm()
    assert llm.provider == "ollama"
    assert llm.model_name == "deepseek-r1:1.5b"


def test_google_without_key_raises() -> None:
    with pytest.raises(ProviderConfigError) as exc:
        make_llm(provider="google")
    assert "GOOGLE_API_KEY" in str(exc.value)


def test_google_with_key_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    llm = make_llm(provider="google")
    assert llm.provider == "google"
    assert llm.model_name == "gemini-2.5-flash"


def test_google_uses_gemini_api_key_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    llm = make_llm(provider="google")
    assert llm.provider == "google"


def test_unknown_provider_raises() -> None:
    with pytest.raises(ProviderConfigError) as exc:
        make_llm(provider="banana")
    assert "Unknown" in str(exc.value)


def test_settings_drives_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When settings.json says ollama, factory picks ollama."""
    import json

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"llm_provider": "ollama", "llm_model": "qwen3-vl:8b"})
    )
    monkeypatch.setenv(
        "YUKI_INDEX_DB", str(tmp_path / "index.db")
    )  # parent of settings.json
    llm = make_llm()
    assert llm.provider == "ollama"


def test_unreliable_tool_models() -> None:
    assert is_tool_call_unreliable("deepseek-r1:1.5b") is True
    assert is_tool_call_unreliable("qwen3-vl:8b") is False
    assert is_tool_call_unreliable("claude-sonnet-4-6") is False
