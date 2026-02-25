"""Project model — top-level domain container."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(BaseModel):
    """A project groups related scenarios within a domain."""

    id: str
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    metadata: dict = Field(default_factory=dict)
