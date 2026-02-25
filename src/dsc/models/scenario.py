"""Scenario model — a self-contained decision domain with lifecycle management."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScenarioStatus(str, Enum):
    """Scenario lifecycle stages. Transitions must follow this order."""

    DRAFT = "draft"
    EXPLORATION = "exploration"
    GRAPH_EXTRACTION = "graph_extraction"
    GRAPH_OPTIMIZATION = "graph_optimization"
    COMPILED = "compiled"
    PRODUCTION = "production"


# Valid lifecycle transitions: each status maps to allowed next statuses
VALID_TRANSITIONS: dict[ScenarioStatus, list[ScenarioStatus]] = {
    ScenarioStatus.DRAFT: [ScenarioStatus.EXPLORATION],
    ScenarioStatus.EXPLORATION: [ScenarioStatus.GRAPH_EXTRACTION],
    ScenarioStatus.GRAPH_EXTRACTION: [ScenarioStatus.GRAPH_OPTIMIZATION],
    ScenarioStatus.GRAPH_OPTIMIZATION: [ScenarioStatus.COMPILED],
    ScenarioStatus.COMPILED: [ScenarioStatus.PRODUCTION, ScenarioStatus.GRAPH_OPTIMIZATION],
    ScenarioStatus.PRODUCTION: [ScenarioStatus.EXPLORATION],
}


class ObservationField(BaseModel):
    """Definition of a single field in the observation schema."""

    type: str  # e.g. "string", "number", "boolean", "object", "array"
    description: str = ""


class ObservationSchema(BaseModel):
    """Schema describing the structure of runtime observations."""

    fields: dict[str, ObservationField] = Field(default_factory=dict)


class ActionDefinition(BaseModel):
    """Definition of an available action in the scenario."""

    name: str
    description: str = ""
    tool: str | None = None  # if this action invokes a tool
    parameters_schema: dict = Field(default_factory=dict)


class ToolDefinition(BaseModel):
    """Definition of an external tool the system can invoke."""

    name: str
    description: str = ""
    parameters_schema: dict = Field(default_factory=dict)
    returns_schema: dict = Field(default_factory=dict)


class Scenario(BaseModel):
    """A self-contained decision domain with full schema definitions.

    Scenarios progress through lifecycle stages from Draft to Production.
    Each stage has preconditions that must be met before advancing.
    """

    id: str
    project_id: str
    name: str
    description: str = ""
    status: ScenarioStatus = ScenarioStatus.DRAFT
    context: str = ""  # domain description for LLM
    observation_schema: ObservationSchema = Field(default_factory=ObservationSchema)
    actions: dict[str, ActionDefinition] = Field(default_factory=dict)
    tools: dict[str, ToolDefinition] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)  # rules the LLM must follow
    trace_ids: list[str] = Field(default_factory=list)
    graph_version: int | None = None
    compiled_version: int | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    metadata: dict = Field(default_factory=dict)
