"""Polish — opt-in Haiku batch summarizer (mocked anthropic)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from yuki.scan.entities import Entity
from yuki.scan.polish import polish, should_polish


def test_should_polish_high_confidence_rich() -> None:
    e = Entity(
        kind="person",
        id="p",
        name="Sarah",
        confidence=0.85,
        attributes={"interaction_frequency": "daily"},
        fact_ids=["f1", "f2", "f3", "f4"],
    )
    assert should_polish(e) is True


def test_should_not_polish_low_confidence() -> None:
    e = Entity(
        kind="person",
        id="p",
        name="Sarah",
        confidence=0.5,
        attributes={},
        fact_ids=["f1", "f2", "f3", "f4"],
    )
    assert should_polish(e) is False


def test_should_not_polish_thin_evidence() -> None:
    e = Entity(
        kind="person",
        id="p",
        name="Sarah",
        confidence=0.9,
        attributes={},
        fact_ids=["f1"],
    )
    assert should_polish(e) is False


def test_polish_calls_anthropic_once() -> None:
    e1 = Entity(
        kind="person",
        id="p1",
        name="Sarah",
        confidence=0.9,
        attributes={"interaction_frequency": "daily"},
        fact_ids=["a", "b", "c", "d"],
    )
    e2 = Entity(
        kind="person",
        id="p2",
        name="Bob",
        confidence=0.9,
        attributes={"interaction_frequency": "weekly"},
        fact_ids=["a", "b", "c", "d"],
    )
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.content = [
        MagicMock(text='{"p1": "Sarah is a daily collaborator.", "p2": "Bob is a weekly peer."}')
    ]
    fake_client.messages.create.return_value = fake_resp

    with patch("yuki.scan.polish._client", return_value=fake_client):
        out = polish([e1, e2])

    assert out["p1"].startswith("Sarah")
    assert fake_client.messages.create.call_count == 1


def test_polish_empty_input_returns_empty() -> None:
    assert polish([]) == {}
