"""Data models for compilability analysis reports."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Compilability(str, Enum):
    """How compilable a decision point is."""

    COMPILABLE = "compilable"
    PARTIALLY_COMPILABLE = "partially_compilable"
    NOT_COMPILABLE = "not_compilable"


class DecisionPoint(BaseModel):
    """A single decision point found in agent code or logs."""

    name: str = Field(description="Name or identifier of the decision point")
    description: str = Field(description="What this decision point does")
    compilability: Compilability
    reason: str = Field(description="Why it is or isn't compilable")
    source_location: str = Field(default="", description="File:line or log cluster ID")
    pattern: str = Field(default="", description="Detected pattern type, e.g. 'router', 'classifier', 'pipeline'")


class SuggestedScenario(BaseModel):
    """A DSC scenario suggested from analysis."""

    name: str
    description: str
    states: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    observation_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, description="How confident we are this is compilable")
    source: str = Field(default="", description="Where this scenario was detected")


class CostEstimate(BaseModel):
    """Estimated cost savings from compilation."""

    current_cost_per_1k: float = Field(description="Estimated LLM cost per 1000 executions ($)")
    compiled_cost_per_1k: float = Field(description="Cost after compiling ($)")
    savings_percent: float
    compile_cost: float = Field(description="One-time cost to compile ($)")
    breakeven_executions: int = Field(description="Executions until compilation pays for itself")


class CompilabilityReport(BaseModel):
    """Full compilability analysis report."""

    source_type: str = Field(description="'code', 'logs', or 'both'")
    overall_score: float = Field(ge=0, le=1, description="0=nothing compilable, 1=fully compilable")

    total_decision_points: int = 0
    compilable_points: int = 0
    partially_compilable_points: int = 0
    not_compilable_points: int = 0

    decision_points: list[DecisionPoint] = Field(default_factory=list)
    scenarios: list[SuggestedScenario] = Field(default_factory=list)
    cost_estimate: CostEstimate | None = None
    warnings: list[str] = Field(default_factory=list)
    raw_analysis: dict[str, Any] = Field(default_factory=dict, description="Raw LLM analysis output")
