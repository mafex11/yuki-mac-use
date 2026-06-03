"""Yuki's own fine-tunes are recommended only when installed locally.

They aren't pullable from a registry yet, so surfacing yuki-1b on a machine
that doesn't have it would produce a failing `ollama pull`. _recommendations_for
gates them on the installed set.
"""

from __future__ import annotations

from yuki.backend.routers.provider import _RECOMMENDED_OLLAMA, _recommendations_for


def test_yuki_finetune_hidden_when_not_installed() -> None:
    recs = _recommendations_for({"qwen2.5:7b", "llama3.2:1b"})
    assert [r["name"] for r in recs] == [r["name"] for r in _RECOMMENDED_OLLAMA]
    assert not any(r["name"] == "yuki-1b" for r in recs)


def test_yuki_finetune_listed_first_when_installed() -> None:
    recs = _recommendations_for({"yuki-1b:latest", "qwen2.5:7b"})
    assert recs[0]["name"] == "yuki-1b"  # local-first default leads
    # the stock recommendations still follow, unchanged
    assert [r["name"] for r in recs[1:]] == [r["name"] for r in _RECOMMENDED_OLLAMA]


def test_matches_base_name_ignoring_tag() -> None:
    # `ollama list` reports tagged names (yuki-1b:latest); match on the base.
    assert any(r["name"] == "yuki-1b"
               for r in _recommendations_for({"yuki-1b:latest"}))
