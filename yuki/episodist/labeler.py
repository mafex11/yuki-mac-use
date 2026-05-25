"""Labeler — produces a short human label for a session.

Pure heuristic: dominant app → label, else dominant browser domain → label,
else "Idle" if only idle events, else "Unknown".
"""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

from yuki.episodist.sessions import Session
from yuki.observer.events import EventKind


def label(session: Session) -> str:
    if not session.events:
        return "Unknown"

    if any(e.kind == EventKind.IDLE_START for e in session.events) and not any(
        e.kind in {EventKind.APP_FOCUS, EventKind.URL_CHANGE} for e in session.events
    ):
        return "Idle"

    apps: Counter[str] = Counter()
    for e in session.events:
        if e.kind == EventKind.APP_FOCUS:
            name = e.payload.get("name") or ""
            if name:
                apps[name] += 1
    if apps:
        top, _ = apps.most_common(1)[0]
        return f"{top} session"

    domains: Counter[str] = Counter()
    for e in session.events:
        if e.kind == EventKind.URL_CHANGE:
            url = e.payload.get("url") or ""
            netloc = urlparse(url).netloc
            if netloc:
                domains[netloc] += 1
    if domains:
        top, _ = domains.most_common(1)[0]
        return top

    return "Unknown"
