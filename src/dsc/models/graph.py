"""Decision graph models — the compiled output of trace extraction."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from dsc.models.conditions import ConditionExpr


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StateDefinition(BaseModel):
    """A state node in the decision graph."""

    name: str
    description: str = ""
    metadata: dict = Field(default_factory=dict)


class Transition(BaseModel):
    """A directed edge in the decision graph.

    Transitions are evaluated in priority order (lower number = higher priority).
    The first transition whose condition matches the observation is taken.
    """

    from_state: str
    condition: ConditionExpr
    action: str
    action_params: dict = Field(default_factory=dict)
    to_state: str
    priority: int = 0
    source_traces: list[str] = Field(default_factory=list)


class DecisionGraph(BaseModel):
    """The complete decision graph for a scenario.

    Contains all states and transitions needed for deterministic execution.
    """

    id: str
    scenario_id: str
    version: int = 1
    states: dict[str, StateDefinition] = Field(default_factory=dict)
    transitions: list[Transition] = Field(default_factory=list)
    initial_state: str
    terminal_states: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
