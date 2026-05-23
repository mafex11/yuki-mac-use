"""memory_write — write or update a note in the vault."""

from __future__ import annotations

from pydantic import ValidationError

from yuki.memory.indexer import Indexer
from yuki.memory.schemas import parse_note
from yuki.memory.vault import Vault

_LOW_CONFIDENCE = 0.7


def memory_write(
    note: dict[str, object],
    body: str,
    *,
    vault: Vault,
    indexer: Indexer,
    update: bool = False,
) -> dict[str, object]:
    """Write or update a note.

    Args:
        note: frontmatter dict; must satisfy a Pydantic note schema.
        body: markdown body.
        vault: Vault instance.
        indexer: open Indexer (so retrieval stays fresh).
        update: if True, allow overwriting an existing note with the same id.

    Returns:
        {id, routed_to, path}. `routed_to` is "90-Inbox" when confidence < 0.7,
        otherwise the section name.

    Raises:
        ValueError: schema validation failure.
    """
    try:
        parsed = parse_note(note)
    except ValidationError as e:
        raise ValueError(f"Invalid note frontmatter: {e}") from e

    if not update:
        existing = vault.resolve_wikilink(parsed.id)
        if existing is not None:
            raise ValueError(
                f"Note {parsed.id!r} already exists at {existing}. Use update=True to overwrite."
            )

    path = vault.write(parsed, body, route_low_confidence=True)
    indexer.upsert(parsed, body, path)

    routed = (
        "90-Inbox"
        if parsed.confidence < _LOW_CONFIDENCE
        else path.parent.relative_to(vault.root).as_posix()
    )
    return {"id": parsed.id, "routed_to": routed, "path": str(path)}
