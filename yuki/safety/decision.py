"""Decision — the result of a confirmation check."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Reason(StrEnum):
    USER = "user"
    USER_EDITED = "user_edited"
    AUTO_READ_ONLY = "auto_read_only"
    AUTO_TRUSTED_ROUTINE = "auto_trusted_routine"
    AUTO_BURST_MODE = "auto_burst_mode"
    SAFETY_FORBIDDEN = "safety_forbidden"


@dataclass
class Decision:
    approved: bool
    payload: dict[str, Any] = field(default_factory=dict)
    reason: Reason = Reason.USER

    @classmethod
    def approve(
        cls,
        payload: dict[str, Any] | None = None,
        reason: Reason = Reason.USER,
    ) -> Decision:
        return cls(approved=True, payload=dict(payload or {}), reason=reason)

    @classmethod
    def deny(cls, reason: Reason = Reason.USER) -> Decision:
        return cls(approved=False, payload={}, reason=reason)
