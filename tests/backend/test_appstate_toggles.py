"""appstate gains learner_enabled + ask_before_remember defaults."""

from __future__ import annotations

from pathlib import Path

import pytest

from yuki.backend import appstate


def test_new_toggle_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    cfg = appstate.load()
    assert cfg["learner_enabled"] is True
    assert cfg["ask_before_remember"] is True


def test_toggles_persist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    cfg = appstate.load()
    cfg["learner_enabled"] = False
    appstate.save(cfg)
    assert appstate.load()["learner_enabled"] is False
    # untouched toggle keeps its default
    assert appstate.load()["ask_before_remember"] is True
