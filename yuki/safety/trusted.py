"""Trusted-routine registry — in-process active routine + success counter."""

from __future__ import annotations

from collections import defaultdict

from yuki.memory.schemas import RoutineNote
from yuki.memory.vault import Vault, VaultError

_PROPOSE_THRESHOLD = 5


class TrustedRoutineRegistry:
    def __init__(self) -> None:
        self._active_id: str | None = None
        self._successes: dict[str, int] = defaultdict(int)

    def enter(self, routine_id: str) -> None:
        v = Vault()
        try:
            note, _ = v.read(routine_id)
        except VaultError:
            return
        if not isinstance(note, RoutineNote) or not note.trusted:
            return
        self._active_id = routine_id

    def exit(self) -> None:
        self._active_id = None

    def is_active(self) -> bool:
        return self._active_id is not None

    def current_id(self) -> str | None:
        return self._active_id

    def record_success(self, routine_id: str) -> bool:
        """Record one success; True if proposal threshold was just crossed."""
        self._successes[routine_id] += 1
        return self._successes[routine_id] == _PROPOSE_THRESHOLD
