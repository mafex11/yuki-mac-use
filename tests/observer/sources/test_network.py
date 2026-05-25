"""NetworkSource: emits only when SSID changes."""

from __future__ import annotations

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.network import NetworkSource


async def test_emits_wifi_change() -> None:
    ssids = iter(["home", "home", "office"])

    async def fake_ssid() -> str | None:
        return next(ssids)

    src = NetworkSource(get_ssid=fake_ssid)
    rb = RingBuffer()
    for _ in range(3):
        await src.iterate(rb)
    out = await rb.drain()
    wifi = [e for e in out if e.kind == EventKind.WIFI_CHANGED]
    assert len(wifi) == 2
    assert wifi[1].payload["ssid"] == "office"
