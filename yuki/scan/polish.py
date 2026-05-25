"""Polish — opt-in Haiku batch summarizer for rich-but-ambiguous entities."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import Any

from yuki.scan.entities import Entity

log = logging.getLogger(__name__)


def _client() -> Any:  # pragma: no cover — real Anthropic client only
    from anthropic import Anthropic

    return Anthropic()


def should_polish(entity: Entity) -> bool:
    return entity.confidence >= 0.7 and len(entity.fact_ids) >= 3


def _payload(entities: list[Entity]) -> str:
    return json.dumps(
        {e.id: {"name": e.name, "kind": e.kind, "attributes": e.attributes} for e in entities},
        indent=2,
    )


def polish(entities: Iterable[Entity]) -> dict[str, str]:
    candidates = [e for e in entities if should_polish(e)]
    if not candidates:
        return {}
    client = _client()
    prompt = (
        "Rewrite each entity's body as one short narrative paragraph. "
        "Reply with JSON: {<entity_id>: <markdown body>, ...}. "
        "Be factual; do not invent details beyond the attributes given."
    )
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=4000,
        messages=[
            {"role": "user", "content": f"{prompt}\n\n{_payload(candidates)}"},
        ],
    )
    try:
        text = resp.content[0].text
        out: dict[str, str] = json.loads(text)
        return out
    except Exception as e:
        log.warning("polish parse failed: %s", e)
        return {}
