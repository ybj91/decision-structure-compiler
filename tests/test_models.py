"""Tests for data model serialization, deserialization, and validation."""

from __future__ import annotations

import json

import pytest

from dsc.models.conditions import (
    AlwaysTrue,
    ConditionGroup,
    FieldCondition,
    LogicOperator,
    Operator,
)
from dsc.models.graph import DecisionGraph, StateDefinition, Transition
from dsc.models.project import Project
from dsc.models.scenario import (
    ActionDefinition,
    ObservationField,
    ObservationSchema,
    Scenario,
    ScenarioStatus,
    ToolDefinition,
)
from dsc.models.trace import ExecutionTrace, TraceSource, TraceStep


# ── Condition AST ───────────────────────────────────────────


class TestFieldCondition:
    def test_basic(self):
        c = FieldCondition(field="user.intent", operator=Operator.EQ, value="refund")
        assert c.type == "field"
        assert c.field == "user.intent"
        assert c.operator == Operator.EQ
        assert c.value == "refund"

    def test_roundtrip(self):
        c = FieldCondition(field="amount", operator=Operator.GTE, value=100)
        data = c.model_dump_json()
        restored = FieldCondition.model_validate_json(data)
        assert restored == c

    def test_all_operators(self):
        for op in Operator:
            c = FieldCondition(field="x", operator=op, value=1)
            assert c.operator == op


class TestConditionGroup:
    def test_and_group(self):
        g = ConditionGroup(
            logic=LogicOperator.AND,
            conditions=[
                FieldCondition(field="intent", operator=Operator.EQ, value="refund"),
                FieldCondition(field="order_age_days", operator=Operator.LTE, value=30),
            ],
        )
        assert g.type == "group"
        assert len(g.conditions) == 2

    def test_nested_groups(self):
        inner = ConditionGroup(
            logic=LogicOperator.OR,
            conditions=[
                FieldCondition(field="a", operator=Operator.EQ, value=1),
                FieldCondition(field="b", operator=Operator.EQ, value=2),
            ],
        )
        outer = ConditionGroup(
            logic=LogicOperator.AND,
            conditions=[
                inner,
                FieldCondition(field="c", operator=Operator.GT, value=0),
            ],
        )
        data = outer.model_dump_json()
        restored = ConditionGroup.model_validate_json(data)
        assert restored == outer

    def test_not_group(self):
        g = ConditionGroup(
            logic=LogicOperator.NOT,
            conditions=[FieldCondition(field="blocked", operator=Operator.EQ, value=True)],
        )
        assert g.logic == LogicOperator.NOT
        assert len(g.conditions) == 1


class TestAlwaysTrue:
    def test_basic(self):
        c = AlwaysTrue()
        assert c.type == "always_true"

    def test_roundtrip(self):
        c = AlwaysTrue()
        data = c.model_dump_json()
        restored = AlwaysTrue.model_validate_json(data)
        assert restored == c


class TestConditionExprDiscriminator:
    """Test that the discriminated union works for deserialization."""

    def test_field_in_transition(self):
        t = Transition(
            from_state="s1",
            condition=FieldCondition(field="x", operator=Operator.EQ, value=1),
            action="do_something",
            to_state="s2",
        )
        data = t.model_dump_json()
        restored = Transition.model_validate_json(data)
        assert isinstance(restored.condition, FieldCondition)

    def test_group_in_transition(self):
        t = Transition(
            from_state="s1",
            condition=ConditionGroup(
                logic=LogicOperator.AND,
                conditions=[
                    FieldCondition(field="a", operator=Operator.EQ, value=1),
                    AlwaysTrue(),
                ],
            ),
            action="act",
            to_state="s2",
        )
        data = t.model_dump_json()
        restored = Transition.model_validate_json(data)
        assert isinstance(restored.condition, ConditionGroup)

    def test_always_true_in_transition(self):
        t = Transition(
            from_state="s1",
            condition=AlwaysTrue(),
            action="default_action",
            to_state="s2",
        )
        data = t.model_dump_json()
        restored = Transition.model_validate_json(data)
        assert isinstance(restored.condition, AlwaysTrue)


# ── Project ─────────────────────────────────────────────────


class TestProject:
    def test_roundtrip(self):
        p = Project(id="proj1", name="Test Project", description="A test")
        data = p.model_dump_json()
        restored = Project.model_validate_json(data)
        assert restored.id == p.id
        assert restored.name == p.name

    def test_defaults(self):
        p = Project(id="p", name="n")
        assert p.description == ""
        assert p.metadata == {}
        assert p.created_at is not None


# ── Scenario ────────────────────────────────────────────────


class TestScenario:
    def test_defaults(self):
        s = Scenario(id="s1", project_id="p1", name="Test")
        assert s.status == ScenarioStatus.DRAFT
        assert s.trace_ids == []
        assert s.graph_version is None

    def test_full_roundtrip(self):
        s = Scenario(
            id="s1",
            project_id="p1",
            name="Customer Support",
            context="Handle customer inquiries",
            observation_schema=ObservationSchema(
                fields={"intent": ObservationField(type="string", description="User intent")}
            ),
            actions={
                "greet": ActionDefinition(name="greet", description="Greet customer"),
                "escalate": ActionDefinition(
                    name="escalate", description="Escalate to human", tool="ticket_system"
                ),
            },
            tools={
                "ticket_system": ToolDefinition(
                    name="ticket_system",
                    description="Create support ticket",
                    parameters_schema={"issue": "string"},
                )
            },
            constraints=["Always be polite", "Never share internal data"],
        )
        data = s.model_dump_json()
        restored = Scenario.model_validate_json(data)
        assert restored.id == s.id
        assert "greet" in restored.actions
        assert restored.tools["ticket_system"].name == "ticket_system"
        assert len(restored.constraints) == 2


# ── Trace ───────────────────────────────────────────────────


class TestTraceStep:
    def test_basic(self):
        step = TraceStep(
            state="greeting",
            observation={"intent": "refund", "order_id": "123"},
            decision="Customer wants a refund, check eligibility",
            action="check_refund_eligibility",
            action_params={"order_id": "123"},
            tool_result={"eligible": True, "amount": 50.0},
            next_state="refund_processing",
        )
        data = step.model_dump_json()
        restored = TraceStep.model_validate_json(data)
        assert restored.state == "greeting"
        assert restored.next_state == "refund_processing"
        assert restored.tool_result["eligible"] is True


class TestExecutionTrace:
    def test_roundtrip(self):
        trace = ExecutionTrace(
            id="t1",
            scenario_id="s1",
            source=TraceSource.LLM,
            initial_state="start",
            steps=[
                TraceStep(
                    state="start",
                    observation={"input": "hello"},
                    action="greet",
                    next_state="awaiting_input",
                ),
                TraceStep(
                    state="awaiting_input",
                    observation={"input": "I want a refund"},
                    action="process_refund",
                    next_state="done",
                ),
            ],
        )
        data = trace.model_dump_json()
        restored = ExecutionTrace.model_validate_json(data)
        assert len(restored.steps) == 2
        assert restored.source == TraceSource.LLM
        assert restored.steps[0].next_state == "awaiting_input"


# ── Decision Graph ──────────────────────────────────────────


class TestDecisionGraph:
    def test_roundtrip(self):
        graph = DecisionGraph(
            id="g1",
            scenario_id="s1",
            version=1,
            states={
                "start": StateDefinition(name="start", description="Initial state"),
                "processing": StateDefinition(name="processing"),
                "done": StateDefinition(name="done"),
            },
            transitions=[
                Transition(
                    from_state="start",
                    condition=FieldCondition(field="intent", operator=Operator.EQ, value="refund"),
                    action="process_refund",
                    to_state="processing",
                    priority=0,
                    source_traces=["t1"],
                ),
                Transition(
                    from_state="start",
                    condition=AlwaysTrue(),
                    action="greet",
                    to_state="start",
                    priority=10,
                ),
                Transition(
                    from_state="processing",
                    condition=FieldCondition(field="approved", operator=Operator.EQ, value=True),
                    action="confirm_refund",
                    to_state="done",
                ),
            ],
            initial_state="start",
            terminal_states=["done"],
        )
        data = graph.model_dump_json()
        restored = DecisionGraph.model_validate_json(data)
        assert len(restored.states) == 3
        assert len(restored.transitions) == 3
        assert restored.initial_state == "start"
        assert isinstance(restored.transitions[0].condition, FieldCondition)
        assert isinstance(restored.transitions[1].condition, AlwaysTrue)


# ── Storage Roundtrip ───────────────────────────────────────


class TestStorageRoundtrip:
    def test_project(self, storage):
        p = Project(id="p1", name="Test")
        storage.save_project(p)
        loaded = storage.load_project("p1")
        assert loaded.id == p.id
        assert loaded.name == p.name

    def test_scenario(self, storage):
        p = Project(id="p1", name="Test")
        storage.save_project(p)
        s = Scenario(id="s1", project_id="p1", name="Scenario 1")
        storage.save_scenario(s)
        loaded = storage.load_scenario("p1", "s1")
        assert loaded.id == "s1"
        assert loaded.status == ScenarioStatus.DRAFT

    def test_trace(self, storage):
        trace = ExecutionTrace(
            id="t1",
            scenario_id="s1",
            initial_state="start",
            steps=[
                TraceStep(state="start", observation={}, action="go", next_state="end"),
            ],
        )
        storage.save_trace("p1", trace)
        loaded = storage.load_trace("p1", "s1", "t1")
        assert loaded.id == "t1"
        assert len(loaded.steps) == 1

    def test_graph(self, storage):
        graph = DecisionGraph(
            id="g1",
            scenario_id="s1",
            version=1,
            states={"start": StateDefinition(name="start")},
            transitions=[],
            initial_state="start",
        )
        storage.save_graph("p1", graph)
        loaded = storage.load_graph("p1", "s1", 1)
        assert loaded.version == 1

    def test_list_projects(self, storage):
        storage.save_project(Project(id="a", name="A"))
        storage.save_project(Project(id="b", name="B"))
        projects = storage.list_projects()
        assert len(projects) == 2

    def test_list_scenarios(self, storage):
        storage.save_project(Project(id="p1", name="P"))
        storage.save_scenario(Scenario(id="s1", project_id="p1", name="S1"))
        storage.save_scenario(Scenario(id="s2", project_id="p1", name="S2"))
        scenarios = storage.list_scenarios("p1")
        assert len(scenarios) == 2

    def test_list_traces(self, storage):
        t1 = ExecutionTrace(id="t1", scenario_id="s1", initial_state="start", steps=[])
        t2 = ExecutionTrace(id="t2", scenario_id="s1", initial_state="start", steps=[])
        storage.save_trace("p1", t1)
        storage.save_trace("p1", t2)
        traces = storage.list_traces("p1", "s1")
        assert len(traces) == 2

    def test_latest_graph_version(self, storage):
        for v in [1, 2, 3]:
            g = DecisionGraph(
                id=f"g{v}", scenario_id="s1", version=v,
                states={"s": StateDefinition(name="s")},
                transitions=[], initial_state="s",
            )
            storage.save_graph("p1", g)
        assert storage.latest_graph_version("p1", "s1") == 3

    def test_delete_project(self, storage):
        storage.save_project(Project(id="p1", name="P"))
        storage.delete_project("p1")
        with pytest.raises(FileNotFoundError):
            storage.load_project("p1")

    def test_not_found(self, storage):
        with pytest.raises(FileNotFoundError):
            storage.load_project("nonexistent")
