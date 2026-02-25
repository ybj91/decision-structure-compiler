"""Tests for the Graph Optimizer."""

from __future__ import annotations

import pytest

from dsc.graph_optimizer.optimizer import GraphOptimizer
from dsc.models.conditions import (
    AlwaysTrue,
    ConditionGroup,
    FieldCondition,
    LogicOperator,
    Operator,
)
from dsc.models.graph import DecisionGraph, StateDefinition, Transition


@pytest.fixture
def optimizer():
    return GraphOptimizer()


def _make_graph(
    states: dict[str, str],
    transitions: list[Transition],
    initial: str = "start",
    terminal: list[str] | None = None,
) -> DecisionGraph:
    """Helper to build a graph from state names/descriptions and transitions."""
    return DecisionGraph(
        id="g1",
        scenario_id="s1",
        states={name: StateDefinition(name=name, description=desc) for name, desc in states.items()},
        transitions=transitions,
        initial_state=initial,
        terminal_states=terminal or [],
    )


class TestRemoveUnreachable:
    def test_removes_unreachable_states(self, optimizer):
        graph = _make_graph(
            states={"start": "", "reachable": "", "orphan": "", "done": ""},
            transitions=[
                Transition(
                    from_state="start",
                    condition=AlwaysTrue(),
                    action="go",
                    to_state="reachable",
                ),
                Transition(
                    from_state="reachable",
                    condition=AlwaysTrue(),
                    action="finish",
                    to_state="done",
                ),
                Transition(
                    from_state="orphan",
                    condition=AlwaysTrue(),
                    action="noop",
                    to_state="orphan",
                ),
            ],
            terminal=["done"],
        )

        optimized, report = optimizer.optimize(graph)
        assert "orphan" not in optimized.states
        assert "orphan" in report.states_removed
        assert len(optimized.states) == 3

    def test_keeps_all_reachable(self, optimizer):
        graph = _make_graph(
            states={"start": "", "mid": "", "end": ""},
            transitions=[
                Transition(from_state="start", condition=AlwaysTrue(), action="go", to_state="mid"),
                Transition(from_state="mid", condition=AlwaysTrue(), action="finish", to_state="end"),
            ],
            terminal=["end"],
        )

        optimized, report = optimizer.optimize(graph)
        assert len(optimized.states) == 3
        assert report.states_removed == []


class TestMergeDuplicateTransitions:
    def test_merges_identical_transitions(self, optimizer):
        cond = FieldCondition(field="x", operator=Operator.EQ, value=1)
        graph = _make_graph(
            states={"start": "", "end": ""},
            transitions=[
                Transition(from_state="start", condition=cond, action="go", to_state="end", source_traces=["t1"]),
                Transition(from_state="start", condition=cond, action="go", to_state="end", source_traces=["t2"]),
            ],
            terminal=["end"],
        )

        optimized, report = optimizer.optimize(graph)
        assert len(optimized.transitions) == 1
        assert report.duplicate_transitions_merged == 1
        # Source traces should be merged
        assert set(optimized.transitions[0].source_traces) == {"t1", "t2"}

    def test_keeps_different_transitions(self, optimizer):
        graph = _make_graph(
            states={"start": "", "a": "", "b": ""},
            transitions=[
                Transition(
                    from_state="start",
                    condition=FieldCondition(field="x", operator=Operator.EQ, value=1),
                    action="go_a",
                    to_state="a",
                ),
                Transition(
                    from_state="start",
                    condition=FieldCondition(field="x", operator=Operator.EQ, value=2),
                    action="go_b",
                    to_state="b",
                ),
            ],
        )

        optimized, report = optimizer.optimize(graph)
        assert len(optimized.transitions) == 2
        assert report.duplicate_transitions_merged == 0


class TestMergeEquivalentStates:
    def test_merges_states_with_same_outgoing(self, optimizer):
        """state_a and state_b both have identical outgoing transitions to 'end'."""
        cond = AlwaysTrue()
        graph = _make_graph(
            states={"start": "", "state_a": "", "state_b": "", "end": ""},
            transitions=[
                Transition(from_state="start", condition=FieldCondition(field="x", operator=Operator.EQ, value=1), action="go_a", to_state="state_a"),
                Transition(from_state="start", condition=FieldCondition(field="x", operator=Operator.EQ, value=2), action="go_b", to_state="state_b"),
                Transition(from_state="state_a", condition=cond, action="finish", to_state="end"),
                Transition(from_state="state_b", condition=cond, action="finish", to_state="end"),
            ],
            terminal=["end"],
        )

        optimized, report = optimizer.optimize(graph)
        # state_a and state_b should be merged
        assert report.final_state_count < report.original_state_count


class TestConflictDetection:
    def test_detects_duplicate_default_transitions(self, optimizer):
        graph = _make_graph(
            states={"start": "", "a": "", "b": ""},
            transitions=[
                Transition(from_state="start", condition=AlwaysTrue(), action="go_a", to_state="a", priority=0),
                Transition(from_state="start", condition=AlwaysTrue(), action="go_b", to_state="b", priority=1),
            ],
        )

        _, report = optimizer.optimize(graph)
        assert len(report.conflicts) > 0
        assert "default transitions" in report.conflicts[0]["reason"].lower() or "identical conditions" in report.conflicts[0]["reason"].lower()

    def test_detects_identical_conditions_different_outcomes(self, optimizer):
        cond = FieldCondition(field="x", operator=Operator.EQ, value=1)
        graph = _make_graph(
            states={"start": "", "a": "", "b": ""},
            transitions=[
                Transition(from_state="start", condition=cond, action="go_a", to_state="a"),
                Transition(from_state="start", condition=cond, action="go_b", to_state="b"),
            ],
        )

        _, report = optimizer.optimize(graph)
        assert len(report.conflicts) > 0

    def test_no_conflicts_for_clean_graph(self, optimizer):
        graph = _make_graph(
            states={"start": "", "a": "", "b": ""},
            transitions=[
                Transition(
                    from_state="start",
                    condition=FieldCondition(field="x", operator=Operator.EQ, value=1),
                    action="go_a",
                    to_state="a",
                ),
                Transition(
                    from_state="start",
                    condition=FieldCondition(field="x", operator=Operator.EQ, value=2),
                    action="go_b",
                    to_state="b",
                ),
            ],
        )

        _, report = optimizer.optimize(graph)
        assert len(report.conflicts) == 0


class TestOptimizationReport:
    def test_report_stats(self, optimizer):
        graph = _make_graph(
            states={"start": "", "mid": "", "end": "", "orphan": ""},
            transitions=[
                Transition(from_state="start", condition=AlwaysTrue(), action="go", to_state="mid"),
                Transition(from_state="mid", condition=AlwaysTrue(), action="done", to_state="end"),
            ],
            terminal=["end"],
        )

        optimized, report = optimizer.optimize(graph)
        assert report.original_state_count == 4
        assert report.final_state_count == 3
        assert report.original_transition_count == 2
        assert "orphan" in report.states_removed
