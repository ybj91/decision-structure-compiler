"""Prompt templates and tool schemas for all LLM interactions.

Each function returns (system_prompt, messages, tool_name, tool_schema) tuples
ready for use with LLMClient.structured_request().
"""

from __future__ import annotations

from typing import Any

from dsc.models.scenario import Scenario


# ── JSON schemas for structured output ──────────────────────

TRACE_STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "state": {"type": "string", "description": "Current state name"},
        "observation": {"type": "object", "description": "Input data at this step"},
        "decision": {"type": "string", "description": "Reasoning for the action taken"},
        "action": {"type": "string", "description": "Action name to execute"},
        "action_params": {"type": "object", "description": "Parameters for the action"},
        "tool_result": {
            "type": ["object", "null"],
            "description": "Result if action invoked a tool, null otherwise",
        },
        "next_state": {"type": "string", "description": "State after action"},
    },
    "required": ["state", "observation", "decision", "action", "action_params", "next_state"],
}

SIMULATE_TRACE_SCHEMA = {
    "type": "object",
    "properties": {
        "initial_state": {"type": "string", "description": "Starting state"},
        "steps": {
            "type": "array",
            "items": TRACE_STEP_SCHEMA,
            "description": "Ordered list of execution steps",
        },
    },
    "required": ["initial_state", "steps"],
}

CONDITION_EXPR_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "type": {"const": "field"},
                "field": {"type": "string", "description": "Dot-path field name in observation"},
                "operator": {
                    "type": "string",
                    "enum": ["eq", "ne", "gt", "lt", "gte", "lte", "in", "not_in", "contains", "matches"],
                },
                "value": {"description": "Value to compare against"},
            },
            "required": ["type", "field", "operator", "value"],
        },
        {
            "type": "object",
            "properties": {
                "type": {"const": "group"},
                "logic": {"type": "string", "enum": ["and", "or", "not"]},
                "conditions": {
                    "type": "array",
                    "description": "Sub-conditions",
                },
            },
            "required": ["type", "logic", "conditions"],
        },
        {
            "type": "object",
            "properties": {"type": {"const": "always_true"}},
            "required": ["type"],
        },
    ]
}

RAW_TRANSITION_SCHEMA = {
    "type": "object",
    "properties": {
        "from_state": {"type": "string"},
        "condition_description": {"type": "string", "description": "Natural language description of when this transition fires"},
        "action": {"type": "string"},
        "action_params": {"type": "object"},
        "to_state": {"type": "string"},
    },
    "required": ["from_state", "condition_description", "action", "to_state"],
}

EXTRACT_TRANSITIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "transitions": {
            "type": "array",
            "items": RAW_TRANSITION_SCHEMA,
        },
    },
    "required": ["transitions"],
}

STATE_MAPPING_SCHEMA = {
    "type": "object",
    "properties": {
        "canonical_states": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Canonical state name"},
                    "description": {"type": "string"},
                    "original_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "All original state names that map to this canonical name",
                    },
                },
                "required": ["name", "description", "original_names"],
            },
        },
    },
    "required": ["canonical_states"],
}

FORMALIZED_TRANSITION_SCHEMA = {
    "type": "object",
    "properties": {
        "from_state": {"type": "string"},
        "condition": CONDITION_EXPR_SCHEMA,
        "action": {"type": "string"},
        "action_params": {"type": "object"},
        "to_state": {"type": "string"},
        "priority": {"type": "integer"},
    },
    "required": ["from_state", "condition", "action", "to_state"],
}

FORMALIZE_CONDITIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "transitions": {
            "type": "array",
            "items": FORMALIZED_TRANSITION_SCHEMA,
        },
        "terminal_states": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["transitions", "terminal_states"],
}


# ── Prompt builders ─────────────────────────────────────────


def _format_scenario_context(scenario: Scenario) -> str:
    """Format scenario details for inclusion in prompts."""
    parts = [f"## Scenario: {scenario.name}"]
    if scenario.context:
        parts.append(f"\n### Context\n{scenario.context}")

    if scenario.observation_schema.fields:
        parts.append("\n### Observation Schema")
        for name, field in scenario.observation_schema.fields.items():
            parts.append(f"- **{name}** ({field.type}): {field.description}")

    if scenario.actions:
        parts.append("\n### Available Actions")
        for name, action in scenario.actions.items():
            tool_note = f" [uses tool: {action.tool}]" if action.tool else ""
            parts.append(f"- **{name}**: {action.description}{tool_note}")

    if scenario.tools:
        parts.append("\n### Available Tools")
        for name, tool in scenario.tools.items():
            parts.append(f"- **{name}**: {tool.description}")

    if scenario.constraints:
        parts.append("\n### Constraints")
        for c in scenario.constraints:
            parts.append(f"- {c}")

    return "\n".join(parts)


def trace_simulation_prompt(
    scenario: Scenario,
    test_input: dict[str, Any],
) -> tuple[str, list[dict], str, dict]:
    """Build prompt for LLM trace simulation.

    Returns (system, messages, tool_name, tool_schema).
    """
    system = (
        "You are a decision process simulator. Given a scenario definition and test input, "
        "simulate a realistic execution trace step by step.\n\n"
        "Rules:\n"
        "- Start from a logical initial state\n"
        "- At each step, evaluate the observation and choose the best action\n"
        "- Record your reasoning in the 'decision' field\n"
        "- Continue until you reach a terminal/completed state\n"
        "- Use only the actions and tools defined in the scenario\n"
        "- Be realistic about tool results\n"
    )

    context = _format_scenario_context(scenario)
    user_msg = (
        f"{context}\n\n"
        f"## Test Input\n```json\n{test_input}\n```\n\n"
        "Simulate a complete execution trace for this input. "
        "Think step by step through the decision process."
    )

    return (
        system,
        [{"role": "user", "content": user_msg}],
        "simulate_trace",
        SIMULATE_TRACE_SCHEMA,
    )


def raw_extraction_prompt(
    scenario: Scenario,
    trace_json: str,
) -> tuple[str, list[dict], str, dict]:
    """Build prompt for Phase A: extracting raw transitions from a single trace."""
    system = (
        "You are a state machine analyst. Given an execution trace, extract all "
        "state transitions as structured tuples.\n\n"
        "For each transition, identify:\n"
        "- from_state: the state before the transition\n"
        "- condition_description: natural language description of what triggered it\n"
        "- action: the action taken\n"
        "- action_params: parameters passed (empty object if none)\n"
        "- to_state: the resulting state\n\n"
        "Focus on extracting the decision logic, not just the sequence."
    )

    context = _format_scenario_context(scenario)
    user_msg = (
        f"{context}\n\n"
        f"## Execution Trace\n```json\n{trace_json}\n```\n\n"
        "Extract all state transitions from this trace."
    )

    return (
        system,
        [{"role": "user", "content": user_msg}],
        "extract_transitions",
        EXTRACT_TRANSITIONS_SCHEMA,
    )


def state_normalization_prompt(
    scenario: Scenario,
    all_states: list[str],
) -> tuple[str, list[dict], str, dict]:
    """Build prompt for Phase B: normalizing/deduplicating states across traces."""
    system = (
        "You are a state normalization expert. Given a list of state names extracted "
        "from multiple execution traces, produce a canonical set of states by:\n\n"
        "1. Identifying states that represent the same concept (synonyms, variants)\n"
        "2. Merging them under a single canonical name\n"
        "3. Providing clear descriptions for each canonical state\n\n"
        "Use clear, consistent naming: lowercase_snake_case."
    )

    context = _format_scenario_context(scenario)
    user_msg = (
        f"{context}\n\n"
        f"## Extracted States\n{all_states}\n\n"
        "Normalize these states into a canonical set. Map each original name to its canonical form."
    )

    return (
        system,
        [{"role": "user", "content": user_msg}],
        "normalize_states",
        STATE_MAPPING_SCHEMA,
    )


def condition_formalization_prompt(
    scenario: Scenario,
    transitions_json: str,
) -> tuple[str, list[dict], str, dict]:
    """Build prompt for Phase C: formalizing conditions into ConditionExpr AST."""
    system = (
        "You are a condition formalization expert. Convert natural language transition "
        "conditions into structured condition expressions.\n\n"
        "Condition types:\n"
        '- field: {"type": "field", "field": "<dot.path>", "operator": "<op>", "value": <val>}\n'
        '  Operators: eq, ne, gt, lt, gte, lte, in, not_in, contains, matches\n'
        '- group: {"type": "group", "logic": "and|or|not", "conditions": [...]}\n'
        '- always_true: {"type": "always_true"} — for default/fallback transitions\n\n'
        "Rules:\n"
        "- Field paths reference the observation schema (e.g., 'intent', 'user.tier')\n"
        "- Use the most specific operator (prefer 'eq' over 'contains' when exact match is possible)\n"
        "- Set priority: lower number = evaluated first. Default transitions should have high priority (e.g., 100)\n"
        "- Mark states with no outgoing transitions as terminal states\n"
    )

    context = _format_scenario_context(scenario)
    user_msg = (
        f"{context}\n\n"
        f"## Transitions to Formalize\n```json\n{transitions_json}\n```\n\n"
        "Convert all condition descriptions into structured condition expressions. "
        "Also identify terminal states."
    )

    return (
        system,
        [{"role": "user", "content": user_msg}],
        "formalize_conditions",
        FORMALIZE_CONDITIONS_SCHEMA,
    )
