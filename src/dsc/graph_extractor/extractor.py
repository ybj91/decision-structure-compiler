"""Three-phase graph extraction pipeline.

Phase A: Extract raw state transitions from each trace
Phase B: Normalize/deduplicate states across traces via LLM
Phase C: Formalize conditions into ConditionExpr AST
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from dsc.llm.client import LLMClient
from dsc.llm.prompts import (
    condition_formalization_prompt,
    raw_extraction_prompt,
    state_normalization_prompt,
)
from dsc.models.conditions import (
    AlwaysTrue,
    ConditionExpr,
    ConditionGroup,
    FieldCondition,
    LogicOperator,
    Operator,
)
from dsc.models.graph import DecisionGraph, StateDefinition, Transition
from dsc.models.scenario import Scenario
from dsc.models.trace import ExecutionTrace


def _parse_condition(data: dict) -> ConditionExpr:
    """Parse a condition expression from raw LLM output dict."""
    ctype = data.get("type", "always_true")

    if ctype == "always_true":
        return AlwaysTrue()

    if ctype == "field":
        return FieldCondition(
            field=data["field"],
            operator=Operator(data["operator"]),
            value=data["value"],
        )

    if ctype == "group":
        return ConditionGroup(
            logic=LogicOperator(data["logic"]),
            conditions=[_parse_condition(c) for c in data.get("conditions", [])],
        )

    # Fallback: treat as always_true
    return AlwaysTrue()


class GraphExtractor:
    """Extracts a DecisionGraph from execution traces using a three-phase LLM pipeline."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    def extract(
        self,
        scenario: Scenario,
        traces: list[ExecutionTrace],
    ) -> DecisionGraph:
        """Run the full three-phase extraction pipeline.

        Phase A: Extract raw transitions from each trace
        Phase B: Normalize states across all traces
        Phase C: Formalize conditions into structured AST

        Returns a DecisionGraph (potentially with redundant transitions —
        use the optimizer to clean it up).
        """
        if not traces:
            raise ValueError("Cannot extract graph from zero traces")

        # Phase A: Raw extraction
        all_raw_transitions: list[dict] = []
        trace_ids: list[str] = []
        for trace in traces:
            raw = self._phase_a_extract(scenario, trace)
            for t in raw:
                t["_trace_id"] = trace.id
            all_raw_transitions.extend(raw)
            trace_ids.append(trace.id)

        # Phase B: State normalization
        all_states = set()
        for t in all_raw_transitions:
            all_states.add(t["from_state"])
            all_states.add(t["to_state"])

        state_mapping, state_definitions = self._phase_b_normalize(
            scenario, sorted(all_states)
        )

        # Apply mapping to transitions
        for t in all_raw_transitions:
            t["from_state"] = state_mapping.get(t["from_state"], t["from_state"])
            t["to_state"] = state_mapping.get(t["to_state"], t["to_state"])

        # Phase C: Condition formalization
        transitions, terminal_states = self._phase_c_formalize(
            scenario, all_raw_transitions
        )

        # Build graph
        initial_state = state_mapping.get(
            traces[0].initial_state, traces[0].initial_state
        )

        # Ensure initial_state is in state_definitions
        if initial_state not in state_definitions:
            state_definitions[initial_state] = StateDefinition(
                name=initial_state, description="Initial state"
            )

        # Ensure all referenced states exist
        for t in transitions:
            if t.from_state not in state_definitions:
                state_definitions[t.from_state] = StateDefinition(name=t.from_state)
            if t.to_state not in state_definitions:
                state_definitions[t.to_state] = StateDefinition(name=t.to_state)

        return DecisionGraph(
            id=uuid.uuid4().hex[:12],
            scenario_id=scenario.id,
            version=1,
            states=state_definitions,
            transitions=transitions,
            initial_state=initial_state,
            terminal_states=terminal_states,
            metadata={
                "source_traces": trace_ids,
                "raw_transition_count": len(all_raw_transitions),
                "final_transition_count": len(transitions),
                "state_count": len(state_definitions),
            },
        )

    def _phase_a_extract(
        self, scenario: Scenario, trace: ExecutionTrace
    ) -> list[dict]:
        """Phase A: Extract raw transitions from a single trace."""
        trace_json = trace.model_dump_json(indent=2)
        system, messages, tool_name, tool_schema = raw_extraction_prompt(
            scenario, trace_json
        )

        result = self.llm.structured_request(
            system=system,
            messages=messages,
            tool_name=tool_name,
            tool_schema=tool_schema,
        )

        return result.get("transitions", [])

    def _phase_b_normalize(
        self, scenario: Scenario, all_states: list[str]
    ) -> tuple[dict[str, str], dict[str, StateDefinition]]:
        """Phase B: Normalize states, returning (mapping, definitions)."""
        system, messages, tool_name, tool_schema = state_normalization_prompt(
            scenario, all_states
        )

        result = self.llm.structured_request(
            system=system,
            messages=messages,
            tool_name=tool_name,
            tool_schema=tool_schema,
        )

        mapping: dict[str, str] = {}
        definitions: dict[str, StateDefinition] = {}

        for canonical in result.get("canonical_states", []):
            name = canonical["name"]
            definitions[name] = StateDefinition(
                name=name,
                description=canonical.get("description", ""),
            )
            for orig in canonical.get("original_names", []):
                mapping[orig] = name

        return mapping, definitions

    def _phase_c_formalize(
        self, scenario: Scenario, raw_transitions: list[dict]
    ) -> tuple[list[Transition], list[str]]:
        """Phase C: Formalize conditions into structured AST."""
        transitions_json = json.dumps(
            [
                {
                    "from_state": t["from_state"],
                    "condition_description": t.get("condition_description", ""),
                    "action": t["action"],
                    "action_params": t.get("action_params", {}),
                    "to_state": t["to_state"],
                }
                for t in raw_transitions
            ],
            indent=2,
        )

        system, messages, tool_name, tool_schema = condition_formalization_prompt(
            scenario, transitions_json
        )

        result = self.llm.structured_request(
            system=system,
            messages=messages,
            tool_name=tool_name,
            tool_schema=tool_schema,
        )

        # Build trace ID mapping for source attribution
        trace_map: dict[str, list[str]] = {}
        for t in raw_transitions:
            key = f"{t['from_state']}→{t['action']}→{t['to_state']}"
            trace_id = t.get("_trace_id", "")
            if trace_id:
                trace_map.setdefault(key, []).append(trace_id)

        transitions = []
        for t_data in result.get("transitions", []):
            condition = _parse_condition(t_data.get("condition", {"type": "always_true"}))
            key = f"{t_data['from_state']}→{t_data['action']}→{t_data['to_state']}"
            transitions.append(
                Transition(
                    from_state=t_data["from_state"],
                    condition=condition,
                    action=t_data["action"],
                    action_params=t_data.get("action_params", {}),
                    to_state=t_data["to_state"],
                    priority=t_data.get("priority", 0),
                    source_traces=trace_map.get(key, []),
                )
            )

        terminal_states = result.get("terminal_states", [])
        return transitions, terminal_states
