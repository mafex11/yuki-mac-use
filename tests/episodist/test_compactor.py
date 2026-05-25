"""Compactor: calls Haiku, parses JSON, applies VaultDiff."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yuki.episodist.compactor import compact_last_week


@pytest.fixture
def vault_with_episodes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    eps = vault / "60-Episodes"
    eps.mkdir(parents=True)
    for d in ("2026-05-15", "2026-05-16", "2026-05-17"):
        (eps / f"{d}.md").write_text(f"# {d}\n\nfocused on Slack and GitHub.\n")
    return vault


def test_calls_haiku_and_applies_diff(vault_with_episodes: Path) -> None:
    fake_resp = MagicMock()
    fake_resp.content = [
        MagicMock(
            text=(
                '{"entries": [{"action":"create","confidence":0.9,'
                '"note":{"id":"routine-morning","type":"routine","name":"Morning",'
                '"schedule":"weekdays 8am","steps":[],"trusted":false}}]}'
            )
        )
    ]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp

    with patch("yuki.episodist.compactor._client", return_value=fake_client):
        result = compact_last_week(today=date(2026, 5, 17))

    assert result.applied == 1
    assert (vault_with_episodes / "30-Routines" / "Morning.md").exists()


def test_no_episodes_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "v"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    (tmp_path / "v" / "60-Episodes").mkdir(parents=True)
    fake_client = MagicMock()
    with patch("yuki.episodist.compactor._client", return_value=fake_client):
        result = compact_last_week(today=date(2026, 5, 17))
    assert result.applied == 0
    fake_client.messages.create.assert_not_called()


def test_haiku_invalid_json_yields_zero_applied(vault_with_episodes: Path) -> None:
    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(text="not json")]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp
    with patch("yuki.episodist.compactor._client", return_value=fake_client):
        result = compact_last_week(today=date(2026, 5, 17))
    assert result.applied == 0
