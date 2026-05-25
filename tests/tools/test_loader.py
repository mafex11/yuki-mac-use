"""Loader: loads user tools, tolerates broken, idempotent re-load."""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from yuki.tools import loader
from yuki.tools.native.registry import REGISTRY


@pytest.fixture(autouse=True)
def isolated_user_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    monkeypatch.setenv("YUKI_USER_TOOLS_DIR", str(tmp_path))
    saved = dict(REGISTRY)
    yield tmp_path
    REGISTRY.clear()
    REGISTRY.update(saved)


def test_loads_user_tool(isolated_user_dir: Path) -> None:
    (isolated_user_dir / "weather.py").write_text(
        textwrap.dedent(
            """
        from yuki import tool, DangerLevel

        @tool(name="weather", danger=DangerLevel.READ_ONLY)
        async def weather(city: str) -> str:
            \"\"\"Pretend to fetch weather.\"\"\"
            return f"sunny in {city}"
    """
        )
    )
    loaded = loader.load_user_tools()
    assert loaded == ["weather.py"]
    assert "weather" in REGISTRY


def test_broken_user_tool_logged_but_does_not_raise(
    isolated_user_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (isolated_user_dir / "broken.py").write_text("syntax !!! error")
    loaded = loader.load_user_tools()
    assert loaded == []
    assert "broken.py" in caplog.text


def test_idempotent_reload(isolated_user_dir: Path) -> None:
    (isolated_user_dir / "x.py").write_text(
        textwrap.dedent(
            """
        from yuki import tool, DangerLevel
        @tool(name="x", danger=DangerLevel.READ_ONLY)
        async def x() -> str:
            \"\"\".\"\"\"
            return ""
    """
        )
    )
    loader.load_user_tools()
    loader.load_user_tools()
    assert "x" in REGISTRY


def test_no_dir_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("YUKI_USER_TOOLS_DIR", str(tmp_path / "nope"))
    assert loader.load_user_tools() == []
