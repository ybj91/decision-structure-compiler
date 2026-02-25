"""Tests for the Trace Collector."""

from __future__ import annotations

import pytest

from dsc.models.project import Project
from dsc.models.trace import ExecutionTrace, TraceSource, TraceStep
from dsc.trace_collector.collector import TraceCollector, TraceValidationError


@pytest.fixture
def collector(storage):
    # Create a project so the storage path exists
    storage.save_project(Project(id="p1", name="Test"))
    return TraceCollector(storage)


def _make_steps(*states: str) -> list[TraceStep]:
    """Helper to create a valid chain of steps from state names."""
    steps = []
    for i in range(len(states) - 1):
        steps.append(
            TraceStep(
                state=states[i],
                observation={"step": i},
                action=f"go_to_{states[i + 1]}",
                next_state=states[i + 1],
            )
        )
    return steps


class TestCreateTrace:
    def test_create_and_retrieve(self, collector):
        steps = _make_steps("start", "middle", "end")
        trace = collector.create_trace("p1", "s1", "start", steps)
        loaded = collector.get_trace("p1", "s1", trace.id)
        assert loaded.initial_state == "start"
        assert len(loaded.steps) == 2

    def test_create_with_metadata(self, collector):
        steps = _make_steps("a", "b")
        trace = collector.create_trace(
            "p1", "s1", "a", steps,
            source=TraceSource.LLM,
            metadata={"test_case": "happy_path"},
        )
        assert trace.source == TraceSource.LLM
        assert trace.metadata["test_case"] == "happy_path"


class TestAddTrace:
    def test_add_valid_trace(self, collector):
        trace = ExecutionTrace(
            id="manual1",
            scenario_id="s1",
            initial_state="start",
            steps=_make_steps("start", "done"),
        )
        result = collector.add_trace("p1", "s1", trace)
        assert result.id == "manual1"
        loaded = collector.get_trace("p1", "s1", "manual1")
        assert loaded.id == "manual1"


class TestTraceValidation:
    def test_empty_steps_rejected(self, collector):
        trace = ExecutionTrace(
            id="t1", scenario_id="s1", initial_state="start", steps=[]
        )
        with pytest.raises(TraceValidationError, match="at least one step"):
            collector.add_trace("p1", "s1", trace)

    def test_initial_state_mismatch_rejected(self, collector):
        trace = ExecutionTrace(
            id="t1",
            scenario_id="s1",
            initial_state="start",
            steps=[TraceStep(state="wrong", observation={}, action="go", next_state="end")],
        )
        with pytest.raises(TraceValidationError, match="does not match initial_state"):
            collector.add_trace("p1", "s1", trace)

    def test_broken_chain_rejected(self, collector):
        trace = ExecutionTrace(
            id="t1",
            scenario_id="s1",
            initial_state="a",
            steps=[
                TraceStep(state="a", observation={}, action="go", next_state="b"),
                TraceStep(state="c", observation={}, action="go", next_state="d"),  # c != b
            ],
        )
        with pytest.raises(TraceValidationError, match="does not match"):
            collector.add_trace("p1", "s1", trace)

    def test_single_step_valid(self, collector):
        trace = ExecutionTrace(
            id="t1",
            scenario_id="s1",
            initial_state="only",
            steps=[TraceStep(state="only", observation={}, action="done", next_state="end")],
        )
        result = collector.add_trace("p1", "s1", trace)
        assert result.id == "t1"


class TestListAndDelete:
    def test_list_traces(self, collector):
        for name in ["t1", "t2", "t3"]:
            trace = ExecutionTrace(
                id=name, scenario_id="s1", initial_state="s",
                steps=[TraceStep(state="s", observation={}, action="a", next_state="e")],
            )
            collector.add_trace("p1", "s1", trace)
        traces = collector.list_traces("p1", "s1")
        assert len(traces) == 3

    def test_delete_trace(self, collector):
        trace = ExecutionTrace(
            id="td", scenario_id="s1", initial_state="s",
            steps=[TraceStep(state="s", observation={}, action="a", next_state="e")],
        )
        collector.add_trace("p1", "s1", trace)
        collector.delete_trace("p1", "s1", "td")
        with pytest.raises(FileNotFoundError):
            collector.get_trace("p1", "s1", "td")
