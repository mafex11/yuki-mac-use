"""BurstMode — short-lived auto-approve window for reversible actions."""

from __future__ import annotations

import time


class BurstMode:
    def __init__(self) -> None:
        self._active_until: float = 0.0

    def engage(self, duration: float = 30.0) -> None:
        self._active_until = max(self._active_until, time.monotonic() + duration)

    def disengage(self) -> None:
        self._active_until = 0.0

    def is_active(self) -> bool:
        return time.monotonic() < self._active_until
