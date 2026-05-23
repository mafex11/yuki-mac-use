"""Pydantic models for the typed note frontmatter.

Every note has a `type` discriminator; `parse_note` returns the right subclass.
The vault/indexer/retriever all speak in `AnyNote` so the schema layer is the
only place note shapes live.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class _Base(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    source: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("id must be lowercase kebab-case slug")
        return v


class PersonContact(BaseModel):
    slack: str | None = None
    email: str | None = None
    phone: str | None = None


class PersonNote(_Base):
    type: Literal["person"]
    name: str
    role: str | None = None
    relationship: Literal["manager", "report", "peer", "external", "personal"] | None = None
    contact: PersonContact = Field(default_factory=PersonContact)
    last_seen: datetime | None = None
    interaction_frequency: Literal["daily", "weekly", "monthly", "rare"] | None = None


class ProjectNote(_Base):
    type: Literal["project"]
    name: str
    status: Literal["active", "paused", "archived"]
    tech: list[str] = Field(default_factory=list)
    path: str | None = None
    last_touched: datetime | None = None


class RoutineNote(_Base):
    type: Literal["routine"]
    name: str
    schedule: str
    steps: list[str] = Field(default_factory=list)
    trusted: bool = False


class AppNote(_Base):
    type: Literal["app"]
    name: str
    bundle_id: str
    importance: Literal["primary", "occasional", "background"]
    common_uses: list[str] = Field(default_factory=list)


class IdentityNote(_Base):
    type: Literal["identity"]
    name: str
    body: str = ""


class PreferenceNote(_Base):
    type: Literal["preference"]
    name: str
    value: str


class KnowledgeNote(_Base):
    type: Literal["knowledge"]
    name: str


class EpisodeNote(_Base):
    type: Literal["episode"]
    date: str  # YYYY-MM-DD


class TriggerCondition(BaseModel):
    kind: Literal["time", "calendar", "app_state", "idle", "deviation", "external"]
    model_config = {"extra": "allow"}


class TriggerAction(BaseModel):
    kind: Literal["routine", "tool_call", "suggestion"]
    model_config = {"extra": "allow"}


class TriggerNote(_Base):
    type: Literal["trigger"]
    enabled: bool
    condition: TriggerCondition
    debounce: str
    action: TriggerAction
    last_fired: datetime | None = None
    fire_count: int = 0
    acceptance_rate: float = Field(default=0.0, ge=0.0, le=1.0)


AnyNote = Annotated[
    PersonNote
    | ProjectNote
    | RoutineNote
    | AppNote
    | IdentityNote
    | PreferenceNote
    | KnowledgeNote
    | EpisodeNote
    | TriggerNote,
    Field(discriminator="type"),
]


class _NoteEnvelope(BaseModel):
    note: AnyNote


def parse_note(data: dict[str, object]) -> AnyNote:
    """Validate a frontmatter dict into the right Note subclass."""
    return _NoteEnvelope(note=data).note  # type: ignore[arg-type]
