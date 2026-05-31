"""app_state.json (non-secret config) + Keychain (api keys) reader.

Resolution for api keys: env var first (dev mode), then macOS Keychain
(bundled-app mode). Config (provider/model/UI prefs) lives in plaintext json
because none of it is sensitive.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

from yuki.memory import paths

log = logging.getLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "llm_provider": "google",
    "llm_model": "gemini-2.5-flash",
    "hud_corner": "top-right",
    "hotkey": "cmd+shift+a",
    "launch_at_login": False,
}

_KEYCHAIN_SERVICE = "com.yuki.app"
_KEY_ENV = {
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": "",
}


def _path():
    return paths.app_support_dir() / "app_state.json"


def load() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("app_state.json unreadable (%s); using defaults", e)
        return dict(_DEFAULTS)
    return {**_DEFAULTS, **data}


def save(cfg: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _keychain_get(account: str) -> str | None:  # pragma: no cover -- real Keychain
    if account not in _KEY_ENV:
        return None
    try:
        out = subprocess.run(
            ["security", "find-generic-password",
             "-s", _KEYCHAIN_SERVICE, "-a", account, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception as e:
        log.warning("keychain read failed for %s: %s", account, type(e).__name__)
    return None


def api_key_for(provider: str) -> str | None:
    env_name = _KEY_ENV.get(provider, "")
    if env_name:
        val = os.environ.get(env_name)
        if val:
            return val
    return _keychain_get(provider)
