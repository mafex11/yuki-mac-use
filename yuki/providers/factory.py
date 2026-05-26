"""LLM provider factory — pick a ChatModel from settings + env.

Resolution order (last wins):
  1. settings.json (~/Library/Application Support/Yuki/settings.json)
  2. YUKI_LLM_PROVIDER / YUKI_LLM_MODEL env vars

Raises ProviderConfigError with a fix hint when an invalid combination is
requested (e.g. google selected but GOOGLE_API_KEY unset).
"""

from __future__ import annotations

import os
from typing import Any

from yuki.providers.base import BaseChatLLM

_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "ollama": "qwen3-vl:8b",
    "google": "gemini-2.5-flash",
}

# Models that may chat but unreliable for tool calls. Surfaced as a warning.
_UNRELIABLE_TOOL_MODELS = {
    "deepseek-r1:1.5b",
}


class ProviderConfigError(RuntimeError):
    """Provider misconfigured — message includes the fix."""


def _resolve(provider_arg: str | None, model_arg: str | None) -> tuple[str, str]:
    """Resolve provider + model from args > env > settings > defaults.

    If the caller forces a provider (via arg or env) without naming a model,
    we use that provider's default — NOT the settings.json model, which may
    belong to a different provider.
    """
    forced_provider = provider_arg or os.environ.get("YUKI_LLM_PROVIDER")
    forced_model = model_arg or os.environ.get("YUKI_LLM_MODEL")

    settings: dict[str, Any] = {}
    if forced_provider is None or forced_model is None:
        try:
            from yuki.backend.routers.settings import _load as _load_settings

            settings = _load_settings()
        except Exception:
            settings = {}

    provider = forced_provider or settings.get("llm_provider", "anthropic")

    if forced_model:
        model = forced_model
    elif forced_provider and forced_provider != settings.get("llm_provider"):
        model = _DEFAULT_MODELS.get(provider, "")
    else:
        model = settings.get("llm_model") or _DEFAULT_MODELS.get(provider, "")

    return provider, model


def make_llm(
    provider: str | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> BaseChatLLM:
    """Construct an LLM instance for the resolved provider.

    Args:
        provider: Override resolution and force this provider.
        model: Override resolution and use this model.
        **kwargs: Forwarded to the provider constructor (e.g. temperature).
    """
    p, m = _resolve(provider, model)

    if p == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ProviderConfigError(
                "anthropic selected but ANTHROPIC_API_KEY is unset. "
                "Set the env var or PUT /settings {llm_provider: ollama} for local."
            )
        from yuki.providers.anthropic import ChatAnthropic

        return ChatAnthropic(model=m, **kwargs)

    if p == "ollama":
        from yuki.providers.ollama.llm import ChatOllama

        return ChatOllama(model=m, **kwargs)

    if p == "google":
        if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
            raise ProviderConfigError(
                "google selected but GOOGLE_API_KEY (or GEMINI_API_KEY) is unset. "
                "Get one at https://aistudio.google.com/apikey and export it."
            )
        from yuki.providers.google import ChatGoogle

        return ChatGoogle(model=m, **kwargs)

    raise ProviderConfigError(
        f"Unknown llm_provider {p!r}. Supported: anthropic, ollama, google."
    )


def is_tool_call_unreliable(model: str) -> bool:
    """Models known to chat fine but flake on tool calls."""
    return model in _UNRELIABLE_TOOL_MODELS
