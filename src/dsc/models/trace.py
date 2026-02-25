"""Execution trace models — capturing full decision paths."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TraceSource(str, Enum):
    """How a trace was generated."""

    USER = "user"
    LLM = "llm"
    HYBRID = "hybrid"


class TraceStep(BaseModel):
    """A single step in an execution trace.

    Captures the full decision context: what state we're in, what we observe,
    what reasoning led to the decision, and what action was taken.
    """

    state: str  # current state name
    observation: dict = Field(default_factory=dict)  # input data at this step
    decision: str = ""  # reasoning (from LLM or human annotation)
    action: str  # action name taken
    action_params: dict = Field(default_factory=dict)
    tool_result: dict | None = None  # result if action invoked a tool
    next_state: str  # resulting state after action


class ExecutionTrace(BaseModel):
    """A complete execution trace through a scenario.

    Contains the full sequence of state transitions from initial state
    to a terminal state (or as far as execution proceeded).
    """

    id: str
    scenario_id: str
    source: TraceSource = TraceSource.USER
    initial_state: str
    steps: list[TraceStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict = Field(default_factory=dict)
