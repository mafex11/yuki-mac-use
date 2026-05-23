"""Smoke test that proves the toolchain end-to-end:
imports work, pytest runs, ruff/mypy will see real code."""

from yuki import __version__
from yuki._smoke import echo


def test_version_is_a_string() -> None:
    assert isinstance(__version__, str)
    assert __version__ == "0.0.1"


def test_echo_returns_input() -> None:
    assert echo("hello") == "hello"
    assert echo("") == ""


def test_echo_rejects_non_string() -> None:
    import pytest

    with pytest.raises(TypeError):
        echo(123)  # type: ignore[arg-type]
