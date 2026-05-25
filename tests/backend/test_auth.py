"""Auth: token generation, verify, get/set."""

from __future__ import annotations

import pytest

from yuki.backend.auth import (
    AuthError,
    generate_token,
    get_active_token,
    set_active_token,
    verify,
)


def test_generated_token_is_long_hex() -> None:
    t = generate_token()
    assert len(t) >= 64
    int(t, 16)


def test_verify_accepts_active_token() -> None:
    set_active_token("abc")
    verify("abc")


def test_verify_rejects_other() -> None:
    set_active_token("abc")
    with pytest.raises(AuthError):
        verify("xyz")


def test_get_active_returns_set_value() -> None:
    set_active_token("zzz")
    assert get_active_token() == "zzz"
