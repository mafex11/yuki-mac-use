"""Per-launch random auth token. Loopback only — token is defense in depth."""

from __future__ import annotations

import secrets

_token: str | None = None
_uds_mode = False


class AuthError(Exception):
    """Token missing or wrong."""


def generate_token() -> str:
    return secrets.token_hex(32)


def set_active_token(token: str) -> None:
    global _token
    _token = token


def get_active_token() -> str | None:
    return _token


def set_uds_mode(enabled: bool) -> None:
    global _uds_mode
    _uds_mode = enabled


def verify(presented: str) -> None:
    if _uds_mode:
        return
    if _token is None or not secrets.compare_digest(_token, presented):
        raise AuthError("invalid token")
