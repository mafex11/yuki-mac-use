"""YAML frontmatter read/write — round-trip safe wrapper over python-frontmatter."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import yaml  # type: ignore[import-untyped]


def loads(text: str) -> tuple[dict[str, object], str]:
    """Parse a markdown string with optional YAML frontmatter."""
    post = frontmatter.loads(text)
    return dict(post.metadata), post.content


def dumps(metadata: dict[str, object], body: str) -> str:
    """Serialize metadata + body back to markdown text."""
    post = frontmatter.Post(body, **metadata)  # type: ignore[arg-type]
    return frontmatter.dumps(post, Dumper=yaml.SafeDumper)


def read_file(path: Path) -> tuple[dict[str, object], str]:
    return loads(path.read_text(encoding="utf-8"))


def write_file(path: Path, metadata: dict[str, object], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(metadata, body), encoding="utf-8")
