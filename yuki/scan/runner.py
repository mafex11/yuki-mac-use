"""Onboarding scan runner — orchestrates the four-stage pipeline."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from yuki.memory.vault import Vault
from yuki.scan import paths
from yuki.scan.collectors.apps import AppsCollector
from yuki.scan.collectors.base import run_collector
from yuki.scan.collectors.browser import BrowserCollector
from yuki.scan.collectors.calendar import CalendarCollector
from yuki.scan.collectors.contacts import ContactsCollector
from yuki.scan.collectors.files import FilesCollector
from yuki.scan.collectors.git import GitCollector
from yuki.scan.collectors.mail import MailCollector
from yuki.scan.collectors.screen_time import ScreenTimeCollector
from yuki.scan.collectors.shell import ShellCollector
from yuki.scan.collectors.system import SystemCollector
from yuki.scan.entities import Entity
from yuki.scan.normalizer import normalize
from yuki.scan.notewriter import write_entities
from yuki.scan.patterns import detect
from yuki.scan.polish import polish

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    skipped: bool
    fact_count: int
    entity_count: int
    written_paths: list[str]


async def _run_collectors() -> None:
    from yuki.scan.collectors.base import Collector

    collectors: list[Collector] = [
        SystemCollector(),
        AppsCollector(),
        ScreenTimeCollector(),
        CalendarCollector(),
        ContactsCollector(),
        MailCollector(),
        FilesCollector(),
        GitCollector(),
        BrowserCollector(),
        ShellCollector(),
    ]
    await asyncio.gather(*[run_collector(c) for c in collectors])


def _polish_safely(entities: list[Entity]) -> dict[str, str]:
    try:
        return polish(entities)
    except Exception as e:
        log.warning("polish failed: %s", e)
        return {}


async def run(*, polish: bool = False, force: bool = False) -> ScanResult:
    sentinel = paths.sentinel_path()
    if sentinel.exists() and not force:
        log.info("scan sentinel exists, skipping")
        return ScanResult(skipped=True, fact_count=0, entity_count=0, written_paths=[])

    await _run_collectors()
    facts = normalize()
    entities = detect(facts)
    sources = sorted({s for f in facts for s in f.sources})
    vault = Vault()
    paths_written = write_entities(entities, vault=vault, sources=sources)

    if polish:
        polished_bodies = _polish_safely(entities)
        for entity_id, body in polished_bodies.items():
            try:
                note, _ = vault.read(entity_id)
                vault.write(note, body)
            except Exception as e:
                log.warning("polish write failed for %s: %s", entity_id, e)

    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("done")
    return ScanResult(
        skipped=False,
        fact_count=len(facts),
        entity_count=len(entities),
        written_paths=[str(p) for p in paths_written],
    )
