import pytest
from fastapi import HTTPException
from yuki.backend import auth
from yuki.backend.server import require_token


def test_uds_mode_skips_token():
    auth.set_uds_mode(False)
    auth.set_uds_mode(True)
    try:
        auth.verify("anything")  # must NOT raise in UDS mode
    finally:
        auth.reset_auth_state()


def test_tcp_mode_still_enforces():
    auth.reset_auth_state()
    auth.set_active_token("secret")
    try:
        with pytest.raises(auth.AuthError):
            auth.verify("wrong")
    finally:
        auth.reset_auth_state()


def test_require_token_bypassed_in_uds_mode():
    auth.reset_auth_state()
    auth.set_uds_mode(True)
    try:
        # No Authorization header — must NOT raise in UDS mode.
        require_token(authorization="")
    finally:
        auth.reset_auth_state()


def test_require_token_enforced_in_tcp_mode():
    auth.reset_auth_state()
    try:
        with pytest.raises(HTTPException):
            require_token(authorization="")
    finally:
        auth.reset_auth_state()
