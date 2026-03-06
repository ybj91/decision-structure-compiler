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

    def merge(self, other: CompilabilityReport) -> CompilabilityReport:
        """Merge two reports (e.g. code + logs) into a combined report.

        Decision points are deduplicated by name. When both reports identify
        the same point, the higher-confidence classification wins. Scenarios
        are merged by name with confidence boost when both sources agree.
        """
        # Merge decision points by name
        points_by_name: dict[str, DecisionPoint] = {}
        for dp in self.decision_points:
            points_by_name[dp.name] = dp
        for dp in other.decision_points:
            if dp.name in points_by_name:
                existing = points_by_name[dp.name]
                # If both agree it's compilable, keep it; otherwise keep the more conservative
                rank = {Compilability.NOT_COMPILABLE: 0, Compilability.PARTIALLY_COMPILABLE: 1, Compilability.COMPILABLE: 2}
                if rank[dp.compilability] > rank[existing.compilability]:
                    points_by_name[dp.name] = dp
            else:
                points_by_name[dp.name] = dp

        merged_points = list(points_by_name.values())

        # Merge scenarios by name, boost confidence when both sources agree
        scenarios_by_name: dict[str, SuggestedScenario] = {}
        for sc in self.scenarios:
            scenarios_by_name[sc.name] = sc
        for sc in other.scenarios:
            if sc.name in scenarios_by_name:
                existing = scenarios_by_name[sc.name]
                # Merge fields and boost confidence
                merged_states = list(dict.fromkeys(existing.states + sc.states))
                merged_actions = list(dict.fromkeys(existing.actions + sc.actions))
                merged_fields = list(dict.fromkeys(existing.observation_fields + sc.observation_fields))
                boosted_confidence = min(1.0, max(existing.confidence, sc.confidence) + 0.1)
                scenarios_by_name[sc.name] = SuggestedScenario(
                    name=sc.name,
                    description=existing.description or sc.description,
                    states=merged_states,
                    actions=merged_actions,
                    observation_fields=merged_fields,
                    confidence=boosted_confidence,
                    source="code+logs",
                )
            else:
                scenarios_by_name[sc.name] = sc

        merged_scenarios = list(scenarios_by_name.values())

        compilable = sum(1 for dp in merged_points if dp.compilability == Compilability.COMPILABLE)
        partial = sum(1 for dp in merged_points if dp.compilability == Compilability.PARTIALLY_COMPILABLE)
        not_comp = sum(1 for dp in merged_points if dp.compilability == Compilability.NOT_COMPILABLE)

        # Weighted average of scores, biased toward the source with more data
        w1 = max(self.total_decision_points, 1)
        w2 = max(other.total_decision_points, 1)
        combined_score = (self.overall_score * w1 + other.overall_score * w2) / (w1 + w2)

        raw = {}
        raw.update(self.raw_analysis)
        raw.update(other.raw_analysis)

        return CompilabilityReport(
            source_type="both",
            overall_score=round(combined_score, 3),
            total_decision_points=len(merged_points),
            compilable_points=compilable,
            partially_compilable_points=partial,
            not_compilable_points=not_comp,
            decision_points=merged_points,
            scenarios=merged_scenarios,
            warnings=self.warnings + other.warnings,
            raw_analysis=raw,
        )
