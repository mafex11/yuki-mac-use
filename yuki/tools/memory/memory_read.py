"""memory_read — load one note (and optionally its linked notes)."""

from __future__ import annotations

import re
from pathlib import Path

from yuki.memory.schemas import AnyNote
from yuki.memory.vault import Vault, VaultError

_WIKILINK = re.compile(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]")


def _to_dict(note: AnyNote, body: str) -> dict[str, object]:
    return {
        "id": note.id,
        "type": note.type,
        "title": getattr(note, "name", note.id),
        "metadata": note.model_dump(mode="json"),
        "body": body,
    }


def memory_read(
    id_or_path: str,
    *,
    vault: Vault,
    expand_links: int = 0,
) -> dict[str, object]:
    """Read one note from the vault.

    Args:
        id_or_path: frontmatter id, filename, or full path on disk.
        vault: Vault instance.
        expand_links: if >=1, inline notes referenced by [[wikilinks]] one hop deep.

    Returns:
        {id, type, title, metadata, body, linked: [<note dict>, ...]}.

    Raises:
        KeyError: if id_or_path doesn't resolve to anything.
    """
    if id_or_path.endswith(".md") and Path(id_or_path).exists():
        path = Path(id_or_path)
        note, body = vault.read_path(path)
    else:
        try:
            note, body = vault.read(id_or_path)
        except VaultError as e:
            raise KeyError(str(e)) from e

    out = _to_dict(note, body)
    out["linked"] = []
    linked: list[dict[str, object]] = []

    if expand_links >= 1:
        seen = {note.id}
        for raw in _WIKILINK.findall(body):
            target = raw.strip()
            try:
                linked_note, linked_body = vault.read(target)
            except VaultError:
                resolved = vault.resolve_wikilink(target)
                if resolved is None:
                    continue
                linked_note, linked_body = vault.read_path(resolved)
            if linked_note.id in seen:
                continue
            seen.add(linked_note.id)
            linked.append(_to_dict(linked_note, linked_body))
    out["linked"] = linked
    return out
