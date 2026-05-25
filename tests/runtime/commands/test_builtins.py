"""Built-in slash commands: registration + behavior."""

from __future__ import annotations

import yuki.runtime.commands.builtins  # noqa: F401 — triggers registration
from yuki.runtime.commands.pipeline import process_user_input
from yuki.runtime.commands.registry import REGISTRY


def test_six_builtins_registered() -> None:
    for name in ("clear", "compact", "help", "cost", "memory", "quit"):
        assert name in REGISTRY


def test_help_returns_local_text() -> None:
    out = process_user_input("/help")
    assert out.kind == "local_text"
    assert "/clear" in out.text
    assert "/compact" in out.text


def test_clear_returns_local_text_marker() -> None:
    out = process_user_input("/clear")
    assert out.kind == "local_text"
    assert "cleared" in out.text.lower()


def test_quit_signals_skip() -> None:
    out = process_user_input("/quit")
    assert out.kind == "skip"
