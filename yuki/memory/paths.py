"""Single source of truth for vault and index DB paths.

Env overrides:
- YUKI_VAULT_DIR — full path to the markdown vault (default ~/YukiVault)
- YUKI_INDEX_DB  — full path to the SQLite index (default
  ~/Library/Application Support/Yuki/index.db)
- YUKI_APP_SUPPORT — full path to the app-support directory (default
  ~/Library/Application Support/Yuki)
"""

from __future__ import annotations

import os
from pathlib import Path

SECTIONS: tuple[str, ...] = (
    "00-Identity",
    "10-People",
    "20-Projects",
    "30-Routines",
    "40-Apps",
    "50-Knowledge",
    "60-Episodes",
    "90-Inbox",
    "30-Routines/triggers",
)


def _home() -> Path:
    return Path(os.environ["HOME"])


def vault_dir() -> Path:
    override = os.environ.get("YUKI_VAULT_DIR")
    if override:
        return Path(override)
    return _home() / "YukiVault"


def index_db_path() -> Path:
    override = os.environ.get("YUKI_INDEX_DB")
    if override:
        return Path(override)
    return _home() / "Library" / "Application Support" / "Yuki" / "index.db"


def app_support_dir() -> Path:
    override = os.environ.get("YUKI_APP_SUPPORT")
    if override:
        return Path(override)
    return _home() / "Library" / "Application Support" / "Yuki"


def socket_path() -> Path:
    return app_support_dir() / "yuki.sock"


def chat_history_path() -> Path:
    return app_support_dir() / "chat_history.jsonl"


def section_path(section: str) -> Path:
    if section not in SECTIONS:
        raise ValueError(f"Unknown section: {section!r}")
    return vault_dir() / section
