"""Event-driven UI settling: wait until AX notifications quiesce.

Replaces fixed post-action sleeps. The WatchDog already receives structure/
property notifications from every app; this tracker timestamps them so the
loop can wait for "no UI churn for `quiet` seconds" instead of guessing.

Semantics per action:
  settle(min_wait, max_wait, quiet):
    - always wait at least `min_wait` (lets the action land at all)
    - then return as soon as no notification arrived in the last `quiet` s
    - never wait longer than `max_wait` total

Fast apps finish in ~min_wait + quiet; slow page loads get up to max_wait —
strictly better than one fixed number for both cases.
"""

from __future__ import annotations

import threading
import time


class SettleTracker:
    """Timestamps AX activity; thread-safe (notifications arrive off-loop)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_event = 0.0

    def notify(self, *_args, **_kwargs) -> None:
        """Callback shape matches WatchDog callbacks (element, notification, pid)."""
        with self._lock:
            self._last_event = time.monotonic()

    def last_event_age(self) -> float:
        with self._lock:
            if self._last_event == 0.0:
                return float("inf")
            return time.monotonic() - self._last_event

    def settle(self, min_wait: float, max_wait: float, quiet: float = 0.15) -> float:
        """Block until the UI quiesces. Returns seconds actually waited."""
        start = time.monotonic()
        if min_wait > 0:
            time.sleep(min_wait)
        while True:
            waited = time.monotonic() - start
            if waited >= max_wait:
                return waited
            if self.last_event_age() >= quiet:
                return waited
            time.sleep(0.05)


# Per-tool (min_wait, max_wait) bounds. min covers the action landing at all;
# max caps pathological churn (video pages emit notifications forever).
SETTLE_BOUNDS: dict[str, tuple[float, float]] = {
    "app_tool": (0.3, 2.5),
    "shortcut_tool": (0.2, 2.0),
    "click_tool": (0.1, 1.5),
    "type_tool": (0.1, 2.0),
    "scroll_tool": (0.1, 0.8),
    "drag_tool": (0.1, 1.0),
    "browser_tool": (0.3, 3.0),
    "spotify_tool": (0.2, 1.5),
    "music_tool": (0.2, 1.5),
    "system_tool": (0.1, 1.0),
}


def bounds_for(tool_name: str) -> tuple[float, float]:
    return SETTLE_BOUNDS.get(tool_name, (0.0, 0.0))
