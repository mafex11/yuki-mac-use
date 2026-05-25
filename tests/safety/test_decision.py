"""Decision: approve, deny, edited payload."""

from __future__ import annotations

from yuki.safety.decision import Decision, Reason


def test_approve_default_payload() -> None:
    d = Decision.approve(payload={"x": 1})
    assert d.approved is True
    assert d.payload == {"x": 1}
    assert d.reason == Reason.USER


def test_deny_carries_reason() -> None:
    d = Decision.deny(reason=Reason.SAFETY_FORBIDDEN)
    assert d.approved is False
    assert d.reason == Reason.SAFETY_FORBIDDEN


def test_modified_payload_round_trip() -> None:
    d = Decision.approve(
        payload={"to": "x@y", "subject": "edited"}, reason=Reason.USER_EDITED
    )
    assert d.payload["subject"] == "edited"
    assert d.reason == Reason.USER_EDITED
