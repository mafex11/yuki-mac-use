"""Detect the human taking over mid-task (focus theft / manual input).

The agent moves the mouse and presses keys itself, so "input happened" alone
means nothing. The reliable human signal is input the agent DIDN'T inject:
we timestamp every agent-injected action, and a CGEvent tap-free heuristic —
comparing the hardware input timeline (Quartz HID idle time) against the
agent's own action log — flags input that occurred while the agent was
between actions.

Cheap and permissionless: CGEventSourceSecondsSinceLastEventType needs no
event tap, no extra TCC grant.
"""

from __future__ import annotations

import threading
import time


class UserSense:
    def __init__(self, grace: float = 0.8) -> None:
        # Input within `grace` seconds after an agent action is attributed
        # to the agent (CGEvent posts show up in the HID timeline too).
        self._grace = grace
        self._lock = threading.Lock()
        self._last_agent_action = 0.0

    def mark_agent_action(self) -> None:
        with self._lock:
            self._last_agent_action = time.monotonic()

    def _hid_idle_seconds(self) -> float:  # pragma: no cover — real macOS
        try:
            import Quartz

            return float(
                Quartz.CGEventSourceSecondsSinceLastEventType(
                    Quartz.kCGEventSourceStateHIDSystemState,
                    Quartz.kCGAnyInputEventType,
                )
            )
        except Exception:
            return float("inf")

    def user_intervened(self) -> bool:
        """True if hardware input arrived that the agent didn't cause."""
        idle = self._hid_idle_seconds()
        with self._lock:
            since_agent = time.monotonic() - self._last_agent_action
        # Input happened `idle` seconds ago. If the agent's last injection was
        # LONGER ago than that (plus grace), a human touched the mouse/keys.
        return idle < since_agent - self._grace
