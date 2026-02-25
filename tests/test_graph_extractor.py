"""Tests for the Graph Extractor — using mocked LLM responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dsc.graph_extractor.extractor import GraphExtractor, _parse_condition
from dsc.models.conditions import (
    AlwaysTrue,
    ConditionGroup,
    FieldCondition,
    LogicOperator,
    Operator,
)
from dsc.models.scenario import Scenario
from dsc.models.trace import ExecutionTrace, TraceStep


@pytest.fixture
def scenario():
    return Scenario(
        id="s1",
        project_id="p1",
        name="Customer Support",
        context="Handle customer inquiries",
    )


@pytest.fixture
def traces():
    return [
        ExecutionTrace(
            id="t1",
            scenario_id="s1",
            initial_state="greeting",
            steps=[
                TraceStep(
                    state="greeting",
                    observation={"intent": "refund"},
                    decision="Customer wants a refund",
                    action="process_refund",
                    next_state="refund_check",
                ),
                TraceStep(
                    state="refund_check",
                    observation={"eligible": True},
                    decision="Eligible for refund",
                    action="confirm_refund",
                    next_state="done",
                ),
            ],
        ),
    ]


class TestParseCondition:
    def test_field(self):
        c = _parse_condition({"type": "field", "field": "x", "operator": "eq", "value": 1})
        assert isinstance(c, FieldCondition)
        assert c.field == "x"
        assert c.operator == Operator.EQ

    def test_group(self):
        c = _parse_condition({
            "type": "group",
            "logic": "and",
            "conditions": [
                {"type": "field", "field": "a", "operator": "eq", "value": 1},
                {"type": "field", "field": "b", "operator": "gt", "value": 0},
            ],
        })
        assert isinstance(c, ConditionGroup)
        assert c.logic == LogicOperator.AND
        assert len(c.conditions) == 2

    def test_always_true(self):
        c = _parse_condition({"type": "always_true"})
        assert isinstance(c, AlwaysTrue)

    def test_unknown_falls_back(self):
        c = _parse_condition({"type": "unknown_thing"})
        assert isinstance(c, AlwaysTrue)


class TestGraphExtractor:
    def test_full_extraction(self, scenario, traces):
        """Test the full three-phase extraction with mocked LLM."""
        mock_llm = MagicMock()

        # Phase A response
        phase_a_response = {
            "transitions": [
                {
                    "from_state": "greeting",
                    "condition_description": "customer wants a refund",
                    "action": "process_refund",
                    "action_params": {},
                    "to_state": "refund_check",
                },
                {
                    "from_state": "refund_check",
                    "condition_description": "customer is eligible for refund",
                    "action": "confirm_refund",
                    "action_params": {},
                    "to_state": "done",
                },
            ]
        }

        # Phase B response
        phase_b_response = {
            "canonical_states": [
                {"name": "greeting", "description": "Initial greeting", "original_names": ["greeting"]},
                {"name": "refund_check", "description": "Checking refund eligibility", "original_names": ["refund_check"]},
                {"name": "done", "description": "Completed", "original_names": ["done"]},
            ]
        }

        # Phase C response
        phase_c_response = {
            "transitions": [
                {
                    "from_state": "greeting",
                    "condition": {"type": "field", "field": "intent", "operator": "eq", "value": "refund"},
                    "action": "process_refund",
                    "action_params": {},
                    "to_state": "refund_check",
                    "priority": 0,
                },
                {
                    "from_state": "refund_check",
                    "condition": {"type": "field", "field": "eligible", "operator": "eq", "value": True},
                    "action": "confirm_refund",
                    "action_params": {},
                    "to_state": "done",
                    "priority": 0,
                },
            ],
            "terminal_states": ["done"],
        }

        mock_llm.structured_request.side_effect = [
            phase_a_response,
            phase_b_response,
            phase_c_response,
        ]

        extractor = GraphExtractor(mock_llm)
        graph = extractor.extract(scenario, traces)

        assert graph.scenario_id == "s1"
        assert graph.initial_state == "greeting"
        assert len(graph.states) == 3
        assert len(graph.transitions) == 2
        assert "done" in graph.terminal_states
        assert isinstance(graph.transitions[0].condition, FieldCondition)
        assert graph.transitions[0].condition.field == "intent"

    def test_empty_traces_raises(self, scenario):
        extractor = GraphExtractor(MagicMock())
        with pytest.raises(ValueError, match="zero traces"):
            extractor.extract(scenario, [])
