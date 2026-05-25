"""Presenter — routes Suggestions to a UI surface based on urgency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass
class Suggestion:
    trigger_id: str
    text: str
    urgency: str
    ts: datetime


class Presenter(Protocol):
    async def present(self, suggestion: Suggestion) -> None: ...


class InMemoryPresenter:
    def __init__(self) -> None:
        self.shown: list[Suggestion] = []

    async def present(self, suggestion: Suggestion) -> None:
        self.shown.append(suggestion)


class MenuBarPresenter:
    """Low urgency — badge on the menu-bar icon. Stub for now."""

    async def present(self, suggestion: Suggestion) -> None:  # pragma: no cover
        log.info("[menubar] %s: %s", suggestion.trigger_id, suggestion.text)


class NotificationPresenter:
    """Medium urgency — UNUserNotificationCenter. Stub for now."""

    async def present(self, suggestion: Suggestion) -> None:  # pragma: no cover
        log.info("[notification] %s: %s", suggestion.trigger_id, suggestion.text)


class ModalPresenter:
    """High urgency — modal in chat overlay. Stub for now."""

    async def present(self, suggestion: Suggestion) -> None:  # pragma: no cover
        log.info("[modal] %s: %s", suggestion.trigger_id, suggestion.text)


def pick_presenter(
    suggestion: Suggestion, presenters: dict[str, Presenter]
) -> Presenter:
    return presenters.get(suggestion.urgency) or presenters["low"]
