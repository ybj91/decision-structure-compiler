"""Bridge from analyzer output to DSC pipeline input.

Converts SuggestedScenarios from compilability reports into real DSC Scenario
objects that can be saved, simulated, and compiled through the standard pipeline.
"""

from __future__ import annotations

import hashlib
from typing import Any

from dsc.analyzer.report import CompilabilityReport, SuggestedScenario
from dsc.models.scenario import (
    ActionDefinition,
    ObservationField,
    ObservationSchema,
    Scenario,
)


def _make_id(name: str) -> str:
    """Generate a short deterministic ID from a name."""
    slug = name.lower().replace(" ", "_").replace("-", "_")
    suffix = hashlib.md5(name.encode()).hexdigest()[:6]
    return f"{slug[:30]}_{suffix}"


def scenario_from_suggestion(
    suggestion: SuggestedScenario,
    project_id: str,
) -> Scenario:
    """Convert a SuggestedScenario into a real DSC Scenario.

    The resulting Scenario has the observation schema, action definitions,
    and context populated from the analysis. It's ready for trace simulation.
    """
    # Build observation schema from detected fields
    fields = {}
    for field_name in suggestion.observation_fields:
        fields[field_name] = ObservationField(
            type="string",  # default; LLM simulation will refine
            description=f"Detected from agent analysis: {field_name}",
        )

    # Build action definitions from detected actions
    actions = {}
    for action_name in suggestion.actions:
        actions[action_name] = ActionDefinition(
            name=action_name,
            description=f"Action detected from agent analysis",
        )

    # Build context that includes the state information
    state_info = ""
    if suggestion.states:
        state_info = f"\nExpected states: {', '.join(suggestion.states)}"

    context = (
        f"{suggestion.description}{state_info}\n"
        f"(Auto-generated from compilability analysis, confidence: {suggestion.confidence:.0%})"
    )

    return Scenario(
        id=_make_id(suggestion.name),
        project_id=project_id,
        name=suggestion.name,
        description=suggestion.description,
        context=context,
        observation_schema=ObservationSchema(fields=fields),
        actions=actions,
        metadata={"source": suggestion.source, "confidence": suggestion.confidence},
    )


def scenarios_from_report(
    report: CompilabilityReport,
    project_id: str,
    min_confidence: float = 0.5,
) -> list[Scenario]:
    """Convert all suggested scenarios from a report into DSC Scenarios.

    Only includes scenarios above the confidence threshold.
    """
    return [
        scenario_from_suggestion(sc, project_id)
        for sc in report.scenarios
        if sc.confidence >= min_confidence
    ]
