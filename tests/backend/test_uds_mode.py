import pytest
from yuki.backend import auth


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
