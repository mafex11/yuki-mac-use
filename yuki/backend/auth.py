"""Per-launch random auth token. Loopback only — token is defense in depth."""

from __future__ import annotations

import secrets

_token: str | None = None


class AuthError(Exception):
    """Token missing or wrong."""


def generate_token() -> str:
    return secrets.token_hex(32)


def set_active_token(token: str) -> None:
    global _token
    _token = token


def get_active_token() -> str | None:
    return _token


def verify(presented: str) -> None:
    if _token is None or not secrets.compare_digest(_token, presented):
        raise AuthError("invalid token")
