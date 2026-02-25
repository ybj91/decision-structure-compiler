"""Tests for the Compiler."""

from __future__ import annotations

import json

import pytest

from dsc.compiler.compiler import CompiledArtifact, Compiler
from dsc.models.conditions import AlwaysTrue, FieldCondition, Operator
from dsc.models.graph import DecisionGraph, StateDefinition, Transition
from dsc.models.project import Project
from dsc.models.scenario import ActionDefinition, Scenario, ToolDefinition


@pytest.fixture
def project(storage):
    p = Project(id="p1", name="Test")
    storage.save_project(p)
    return p


@pytest.fixture
def scenario(storage, project):
    s = Scenario(
        id="s1",
        project_id=project.id,
        name="Test Scenario",
        actions={
            "greet": ActionDefinition(name="greet", description="Greet user"),
            "escalate": ActionDefinition(
                name="escalate", description="Escalate", tool="tickets"
            ),
        },
        tools={
            "tickets": ToolDefinition(name="tickets", description="Ticket system"),
        },
    )
    storage.save_scenario(s)
    return s


@pytest.fixture
def graph(scenario):
    return DecisionGraph(
        id="g1",
        scenario_id=scenario.id,
        version=1,
        states={
            "start": StateDefinition(name="start", description="Initial"),
            "done": StateDefinition(name="done", description="Completed"),
        },
        transitions=[
            Transition(
                from_state="start",
                condition=FieldCondition(field="intent", operator=Operator.EQ, value="hello"),
                action="greet",
                to_state="done",
                priority=0,
            ),
            Transition(
                from_state="start",
                condition=AlwaysTrue(),
                action="escalate",
                to_state="done",
                priority=10,
            ),
        ],
        initial_state="start",
        terminal_states=["done"],
        metadata={"source_traces": ["t1"]},
    )


class TestCompiler:
    def test_compile_produces_artifact(self, storage, project, scenario, graph):
        compiler = Compiler(storage)
        artifact = compiler.compile(project.id, scenario, graph)

        assert artifact.version == 1
        assert artifact.scenario_id == "s1"
        assert artifact.data["format"] == "dsc-compiled-v1"

    def test_artifact_contains_graph(self, storage, project, scenario, graph):
        compiler = Compiler(storage)
        artifact = compiler.compile(project.id, scenario, graph)

        g = artifact.data["graph"]
        assert g["initial_state"] == "start"
        assert "done" in g["terminal_states"]
        assert len(g["states"]) == 2
        assert len(g["transitions"]) == 2

    def test_artifact_contains_actions_and_tools(self, storage, project, scenario, graph):
        compiler = Compiler(storage)
        artifact = compiler.compile(project.id, scenario, graph)

        assert "greet" in artifact.data["actions"]
        assert "tickets" in artifact.data["tools"]
        assert artifact.data["actions"]["escalate"]["tool"] == "tickets"

    def test_transitions_sorted_by_priority(self, storage, project, scenario, graph):
        compiler = Compiler(storage)
        artifact = compiler.compile(project.id, scenario, graph)

        transitions = artifact.data["graph"]["transitions"]
        priorities = [t["priority"] for t in transitions]
        assert priorities == sorted(priorities)

    def test_version_increments(self, storage, project, scenario, graph):
        compiler = Compiler(storage)
        a1 = compiler.compile(project.id, scenario, graph)
        a2 = compiler.compile(project.id, scenario, graph)
        assert a1.version == 1
        assert a2.version == 2

    def test_artifact_persisted(self, storage, project, scenario, graph):
        compiler = Compiler(storage)
        compiler.compile(project.id, scenario, graph)

        loaded = storage.load_compiled(project.id, scenario.id, 1)
        data = json.loads(loaded)
        assert data["version"] == 1
        assert data["scenario_id"] == "s1"

    def test_artifact_roundtrip(self, storage, project, scenario, graph):
        compiler = Compiler(storage)
        artifact = compiler.compile(project.id, scenario, graph)

        json_str = artifact.to_json()
        restored = CompiledArtifact.from_json(json_str)
        assert restored.version == artifact.version
        assert restored.data["graph"]["initial_state"] == "start"
