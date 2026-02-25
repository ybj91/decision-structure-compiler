"""Tests for the Runtime Engine with pre-built compiled artifacts."""

from __future__ import annotations

import json

import pytest

from dsc.compiler.compiler import CompiledArtifact
from dsc.runtime.engine import RuntimeConfig, RuntimeEngine, StepResult, UnmatchedStateError


def _make_artifact(
    transitions: list[dict],
    states: dict | None = None,
    initial: str = "start",
    terminal: list[str] | None = None,
    actions: dict | None = None,
) -> CompiledArtifact:
    """Helper to build a compiled artifact for testing."""
    if states is None:
        # Auto-generate states from transitions
        state_names = set()
        for t in transitions:
            state_names.add(t["from_state"])
            state_names.add(t["to_state"])
        states = {s: {"name": s, "description": "", "metadata": {}} for s in state_names}

    return CompiledArtifact({
        "format": "dsc-compiled-v1",
        "version": 1,
        "scenario_id": "test",
        "scenario_name": "Test",
        "compiled_at": "2024-01-01T00:00:00Z",
        "graph": {
            "initial_state": initial,
            "terminal_states": terminal or [],
            "states": states,
            "transitions": transitions,
        },
        "actions": actions or {},
        "tools": {},
        "metadata": {},
    })


# ── A realistic customer support scenario ────────────────────

@pytest.fixture
def support_artifact():
    """Customer support routing: greeting → {refund, inquiry, escalation} → done."""
    return _make_artifact(
        transitions=[
            {
                "from_state": "greeting",
                "condition": {"type": "field", "field": "intent", "operator": "eq", "value": "refund"},
                "action": "process_refund",
                "action_params": {},
                "to_state": "refund_check",
                "priority": 0,
            },
            {
                "from_state": "greeting",
                "condition": {"type": "field", "field": "intent", "operator": "eq", "value": "inquiry"},
                "action": "answer_inquiry",
                "action_params": {},
                "to_state": "done",
                "priority": 1,
            },
            {
                "from_state": "greeting",
                "condition": {"type": "always_true"},
                "action": "escalate",
                "action_params": {},
                "to_state": "done",
                "priority": 10,
            },
            {
                "from_state": "refund_check",
                "condition": {"type": "field", "field": "eligible", "operator": "eq", "value": True},
                "action": "approve_refund",
                "action_params": {},
                "to_state": "done",
                "priority": 0,
            },
            {
                "from_state": "refund_check",
                "condition": {"type": "field", "field": "eligible", "operator": "eq", "value": False},
                "action": "deny_refund",
                "action_params": {},
                "to_state": "done",
                "priority": 1,
            },
        ],
        initial="greeting",
        terminal=["done"],
    )


class TestEngineLifecycle:
    def test_start(self, support_artifact):
        engine = RuntimeEngine.from_artifact(support_artifact)
        assert not engine.is_started
        state = engine.start()
        assert state == "greeting"
        assert engine.is_started
        assert not engine.is_terminal

    def test_step_before_start_raises(self, support_artifact):
        engine = RuntimeEngine.from_artifact(support_artifact)
        with pytest.raises(RuntimeError, match="not started"):
            engine.step({"intent": "refund"})

    def test_step_after_terminal_raises(self, support_artifact):
        engine = RuntimeEngine.from_artifact(support_artifact)
        engine.start()
        engine.step({"intent": "inquiry"})
        assert engine.is_terminal
        with pytest.raises(RuntimeError, match="terminal state"):
            engine.step({"intent": "refund"})


class TestStepExecution:
    def test_refund_path(self, support_artifact):
        engine = RuntimeEngine.from_artifact(support_artifact)
        engine.start()

        r1 = engine.step({"intent": "refund"})
        assert r1.action == "process_refund"
        assert r1.to_state == "refund_check"
        assert engine.current_state == "refund_check"

        r2 = engine.step({"eligible": True})
        assert r2.action == "approve_refund"
        assert r2.to_state == "done"
        assert engine.is_terminal

    def test_inquiry_path(self, support_artifact):
        engine = RuntimeEngine.from_artifact(support_artifact)
        engine.start()

        result = engine.step({"intent": "inquiry"})
        assert result.action == "answer_inquiry"
        assert engine.is_terminal

    def test_default_fallback(self, support_artifact):
        engine = RuntimeEngine.from_artifact(support_artifact)
        engine.start()

        result = engine.step({"intent": "unknown_intent"})
        assert result.action == "escalate"
        assert engine.is_terminal

    def test_priority_ordering(self, support_artifact):
        """Specific match (priority 0) should win over default (priority 10)."""
        engine = RuntimeEngine.from_artifact(support_artifact)
        engine.start()

        result = engine.step({"intent": "refund"})
        assert result.action == "process_refund"  # Not escalate


class TestUnmatchedState:
    def test_no_match_raises(self):
        artifact = _make_artifact(
            transitions=[
                {
                    "from_state": "start",
                    "condition": {"type": "field", "field": "x", "operator": "eq", "value": 1},
                    "action": "go",
                    "to_state": "end",
                    "priority": 0,
                },
            ],
            initial="start",
            terminal=["end"],
        )
        engine = RuntimeEngine.from_artifact(artifact)
        engine.start()
        with pytest.raises(UnmatchedStateError):
            engine.step({"x": 999})


class TestConditionTypes:
    def test_group_and(self):
        artifact = _make_artifact(
            transitions=[
                {
                    "from_state": "start",
                    "condition": {
                        "type": "group",
                        "logic": "and",
                        "conditions": [
                            {"type": "field", "field": "a", "operator": "eq", "value": 1},
                            {"type": "field", "field": "b", "operator": "gt", "value": 0},
                        ],
                    },
                    "action": "matched",
                    "to_state": "end",
                    "priority": 0,
                },
            ],
            initial="start",
            terminal=["end"],
        )
        engine = RuntimeEngine.from_artifact(artifact)
        engine.start()
        result = engine.step({"a": 1, "b": 5})
        assert result.action == "matched"

    def test_group_or(self):
        artifact = _make_artifact(
            transitions=[
                {
                    "from_state": "start",
                    "condition": {
                        "type": "group",
                        "logic": "or",
                        "conditions": [
                            {"type": "field", "field": "vip", "operator": "eq", "value": True},
                            {"type": "field", "field": "score", "operator": "gte", "value": 90},
                        ],
                    },
                    "action": "premium",
                    "to_state": "end",
                    "priority": 0,
                },
            ],
            initial="start",
            terminal=["end"],
        )
        engine = RuntimeEngine.from_artifact(artifact)

        engine.start()
        result = engine.step({"vip": True, "score": 50})
        assert result.action == "premium"

    def test_nested_field_paths(self):
        artifact = _make_artifact(
            transitions=[
                {
                    "from_state": "start",
                    "condition": {"type": "field", "field": "user.tier", "operator": "eq", "value": "gold"},
                    "action": "gold_treatment",
                    "to_state": "end",
                    "priority": 0,
                },
            ],
            initial="start",
            terminal=["end"],
        )
        engine = RuntimeEngine.from_artifact(artifact)
        engine.start()
        result = engine.step({"user": {"tier": "gold"}})
        assert result.action == "gold_treatment"


class TestActionHandler:
    def test_custom_handler(self, support_artifact):
        actions_log = []

        def handler(action: str, params: dict):
            actions_log.append(action)
            return {"status": "ok"}

        config = RuntimeConfig(action_handler=handler)
        engine = RuntimeEngine.from_artifact(support_artifact, config)
        engine.start()

        result = engine.step({"intent": "refund"})
        assert actions_log == ["process_refund"]
        assert result.action_result == {"status": "ok"}


class TestRunMultiple:
    def test_run(self, support_artifact):
        engine = RuntimeEngine.from_artifact(support_artifact)
        engine.start()

        results = engine.run([
            {"intent": "refund"},
            {"eligible": True},
        ])

        assert len(results) == 2
        assert results[0].action == "process_refund"
        assert results[1].action == "approve_refund"
        assert engine.is_terminal

    def test_run_stops_at_terminal(self, support_artifact):
        engine = RuntimeEngine.from_artifact(support_artifact)
        engine.start()

        results = engine.run([
            {"intent": "inquiry"},
            {"should_not": "be_processed"},
        ])

        assert len(results) == 1
        assert engine.is_terminal


class TestHistory:
    def test_history_recorded(self, support_artifact):
        engine = RuntimeEngine.from_artifact(support_artifact)
        engine.start()
        engine.step({"intent": "refund"})
        engine.step({"eligible": True})

        assert engine.step_count == 2
        assert len(engine.history) == 2
        assert engine.history[0].from_state == "greeting"
        assert engine.history[1].from_state == "refund_check"


class TestMaxSteps:
    def test_max_steps_enforced(self):
        """Create a cycle and verify max_steps prevents infinite loop."""
        artifact = _make_artifact(
            transitions=[
                {
                    "from_state": "loop",
                    "condition": {"type": "always_true"},
                    "action": "loop_action",
                    "to_state": "loop",
                    "priority": 0,
                },
            ],
            initial="loop",
        )
        config = RuntimeConfig(max_steps=5)
        engine = RuntimeEngine.from_artifact(artifact, config)
        engine.start()

        for _ in range(5):
            engine.step({})

        with pytest.raises(RuntimeError, match="Max steps"):
            engine.step({})


class TestFromJson:
    def test_from_json(self, support_artifact):
        json_str = support_artifact.to_json()
        engine = RuntimeEngine.from_json(json_str)
        engine.start()
        result = engine.step({"intent": "refund"})
        assert result.action == "process_refund"
