"""Provider factory: env > settings > defaults; clear errors on misconfig."""

from __future__ import annotations

from pathlib import Path

import pytest

from yuki.providers.factory import (
    ProviderConfigError,
    default_thinking_budget_for,
    is_tool_call_unreliable,
    make_llm,
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin app support dir so app_state.json doesn't leak between tests."""
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.delenv("YUKI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("YUKI_LLM_MODEL", raising=False)
    monkeypatch.delenv("YUKI_THINKING_BUDGET", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_default_provider_is_google_and_errors_without_key() -> None:
    """Default is now google (from appstate), not anthropic."""
    with pytest.raises(ProviderConfigError) as exc:
        make_llm()
    assert "GOOGLE_API_KEY" in str(exc.value)


def test_anthropic_with_key_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force anthropic via arg (default is now google)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    llm = make_llm(provider="anthropic")
    assert llm.provider == "anthropic"
    assert llm.model_name == "claude-sonnet-4-6"


def test_env_override_to_ollama() -> None:
    llm = make_llm(provider="ollama")
    assert llm.provider == "ollama"
    # Default Ollama model — qwen2.5:7b (validated 0.90 on the agent eval suite).
    assert llm.model_name == "qwen2.5:7b"


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


def test_appstate_drives_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When app_state.json says ollama, factory picks ollama."""
    import json

    appstate_path = tmp_path / "app_state.json"
    appstate_path.write_text(
        json.dumps({"llm_provider": "ollama", "llm_model": "qwen3-vl:8b"})
    )
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    llm = make_llm()
    assert llm.provider == "ollama"


def test_unreliable_tool_models() -> None:
    assert is_tool_call_unreliable("deepseek-r1:1.5b") is True
    assert is_tool_call_unreliable("qwen3-vl:8b") is False
    assert is_tool_call_unreliable("claude-sonnet-4-6") is False


# --- Extended thinking defaults (Spec R, Workstream 1) ---------------------


def test_thinking_budget_default_for_anthropic() -> None:
    """Cloud Anthropic models get a thinking budget by default (>= 1024)."""
    assert default_thinking_budget_for("anthropic", "claude-sonnet-4-6") >= 1024


def test_thinking_budget_default_for_gemini_25() -> None:
    """Gemini 2.5 models support thinking → get a budget."""
    assert default_thinking_budget_for("google", "gemini-2.5-flash") >= 1024


def test_no_thinking_budget_for_gemini_non_25() -> None:
    """Older Gemini (non-2.5) doesn't support thinking → no budget."""
    assert default_thinking_budget_for("google", "gemini-1.5-flash") is None


def test_no_thinking_budget_for_ollama() -> None:
    """Local models don't get thinking by default (slow/unreliable)."""
    assert default_thinking_budget_for("ollama", "qwen2.5:7b") is None


def test_make_llm_anthropic_enables_thinking_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """make_llm wires the default thinking budget into the Anthropic LLM."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    llm = make_llm(provider="anthropic")
    assert llm.thinking_budget is not None
    assert llm.thinking_budget >= 1024


def test_make_llm_thinking_can_be_disabled_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """YUKI_THINKING_BUDGET=0 turns thinking off (escape hatch)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("YUKI_THINKING_BUDGET", "0")
    llm = make_llm(provider="anthropic")
    assert llm.thinking_budget is None


def test_make_llm_explicit_thinking_budget_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit thinking_budget kwarg overrides the default."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    llm = make_llm(provider="anthropic", thinking_budget=4096)
    assert llm.thinking_budget == 4096


def test_make_llm_ollama_no_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama path doesn't get a thinking budget injected."""
    llm = make_llm(provider="ollama")
    # ChatOllama has no thinking_budget attr (or it's None); either way not set.
    assert getattr(llm, "thinking_budget", None) is None
