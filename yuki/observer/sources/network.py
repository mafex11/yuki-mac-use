"""Network source — emits WIFI_CHANGED on SSID change."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


async def _default_get_ssid() -> str | None:  # pragma: no cover — real macOS only
    try:
        from CoreWLAN import CWInterface  # type: ignore[import-untyped]

        ifc = CWInterface.interface()
        return str(ifc.ssid()) if ifc and ifc.ssid() else None
    except Exception:
        return None


class NetworkSource(Source):
    name = "network"

    def __init__(
        self,
        get_ssid: Callable[[], Awaitable[str | None]] | None = None,
    ) -> None:
        super().__init__()
        self._get_ssid = get_ssid or _default_get_ssid
        self._last_ssid: str | None = None

    async def iterate(self, buffer: RingBuffer) -> None:
        ssid = await self._get_ssid()
        if ssid == self._last_ssid:
            return
        self._last_ssid = ssid
        await buffer.push(
            Event(
                ts=datetime.now(UTC),
                kind=EventKind.WIFI_CHANGED,
                payload={"ssid": ssid},
            )
        )
