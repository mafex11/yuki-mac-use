"""Forward-only, idempotent schema migrations.

CURRENT_SCHEMA is the version the running code expects. run_migrations reads
the stored version from app_state.json, runs each migration > stored, and
stamps the new version. v0.1 ships at schema 1 with nothing to migrate.
"""

from __future__ import annotations

import logging

from yuki.backend import appstate

log = logging.getLogger(__name__)

CURRENT_SCHEMA = 1

# Ordered (version, callable) migrations. Each takes no args, is idempotent.
_MIGRATIONS: list[tuple[int, object]] = []


def run_migrations() -> list[int]:
    cfg = appstate.load()
    stored = int(cfg.get("schema_version", 1))
    applied: list[int] = []
    for version, fn in _MIGRATIONS:
        if version > stored:
            log.info("running migration to schema %d", version)
            fn()  # type: ignore[operator]
            applied.append(version)
    if applied or stored != CURRENT_SCHEMA:
        cfg["schema_version"] = CURRENT_SCHEMA
        appstate.save(cfg)
    return applied
