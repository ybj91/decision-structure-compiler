"""Deterministic runtime engine for compiled decision graphs.

The engine loads a compiled artifact and executes it step-by-step:
1. Receives an observation
2. Evaluates transitions from current state (sorted by priority)
3. Takes the first matching transition
4. Dispatches the action
5. Advances to the next state
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from dsc.compiler.compiler import CompiledArtifact
from dsc.models.conditions import (
    AlwaysTrue,
    ConditionExpr,
    ConditionGroup,
    FieldCondition,
    LogicOperator,
    Operator,
)
from dsc.runtime.evaluator import evaluate


class UnmatchedStateError(Exception):
    """No transition matched the current state+observation."""


@dataclass
class StepResult:
    """Result of a single runtime execution step."""

    from_state: str
    observation: dict
    matched_transition: dict | None
    action: str
    action_params: dict
    action_result: Any
    to_state: str


@dataclass
class RuntimeConfig:
    """Configuration for the runtime engine."""

    llm_fallback_enabled: bool = False
    max_steps: int = 1000  # safety limit
    action_handler: Callable[[str, dict], Any] | None = None


def _parse_condition(data: dict) -> ConditionExpr:
    """Parse a condition from compiled artifact format."""
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

    return AlwaysTrue()


class RuntimeEngine:
    """Executes a compiled decision graph deterministically.

    Usage:
        engine = RuntimeEngine.from_artifact(artifact)
        engine.start()
        result = engine.step({"intent": "refund", "order_age": 5})
        while not engine.is_terminal:
            result = engine.step(next_observation)
    """

    def __init__(self, artifact: CompiledArtifact, config: RuntimeConfig | None = None) -> None:
        self.config = config or RuntimeConfig()
        self._graph = artifact.data["graph"]
        self._actions = artifact.data.get("actions", {})
        self._tools = artifact.data.get("tools", {})
        self._metadata = artifact.data.get("metadata", {})

        # Parse transitions grouped by from_state
        self._transitions: dict[str, list[tuple[ConditionExpr, dict]]] = {}
        for t in self._graph["transitions"]:
            state = t["from_state"]
            condition = _parse_condition(t["condition"])
            self._transitions.setdefault(state, []).append((condition, t))

        self._current_state: str | None = None
        self._step_count: int = 0
        self._history: list[StepResult] = []

    @classmethod
    def from_artifact(cls, artifact: CompiledArtifact, config: RuntimeConfig | None = None) -> RuntimeEngine:
        return cls(artifact, config)

    @classmethod
    def from_json(cls, json_str: str, config: RuntimeConfig | None = None) -> RuntimeEngine:
        artifact = CompiledArtifact.from_json(json_str)
        return cls(artifact, config)

    @property
    def current_state(self) -> str | None:
        return self._current_state

    @property
    def is_started(self) -> bool:
        return self._current_state is not None

    @property
    def is_terminal(self) -> bool:
        if self._current_state is None:
            return False
        return self._current_state in self._graph.get("terminal_states", [])

    @property
    def history(self) -> list[StepResult]:
        return list(self._history)

    @property
    def step_count(self) -> int:
        return self._step_count

    def start(self) -> str:
        """Initialize the engine at the graph's initial state.

        Returns the initial state name.
        """
        self._current_state = self._graph["initial_state"]
        self._step_count = 0
        self._history = []
        return self._current_state

    def step(self, observation: dict) -> StepResult:
        """Execute one step: evaluate transitions and advance state.

        Raises UnmatchedStateError if no transition matches and no fallback
        is available.
        """
        if self._current_state is None:
            raise RuntimeError("Engine not started. Call start() first.")

        if self.is_terminal:
            raise RuntimeError(f"Engine is in terminal state '{self._current_state}'")

        if self._step_count >= self.config.max_steps:
            raise RuntimeError(f"Max steps ({self.config.max_steps}) exceeded")

        from_state = self._current_state
        transitions = self._transitions.get(from_state, [])

        # Evaluate transitions in priority order (already sorted in compiled artifact)
        matched_transition = None
        for condition, t_data in transitions:
            if evaluate(condition, observation):
                matched_transition = t_data
                break

        if matched_transition is None:
            raise UnmatchedStateError(
                f"No transition matched from state '{from_state}' "
                f"with observation: {observation}"
            )

        action = matched_transition["action"]
        action_params = matched_transition.get("action_params", {})
        to_state = matched_transition["to_state"]

        # Dispatch action
        action_result = None
        if self.config.action_handler:
            action_result = self.config.action_handler(action, action_params)

        result = StepResult(
            from_state=from_state,
            observation=observation,
            matched_transition=matched_transition,
            action=action,
            action_params=action_params,
            action_result=action_result,
            to_state=to_state,
        )

        self._current_state = to_state
        self._step_count += 1
        self._history.append(result)

        return result

    def run(self, observations: list[dict]) -> list[StepResult]:
        """Run multiple steps sequentially.

        Stops early if a terminal state is reached.
        """
        results = []
        for obs in observations:
            if self.is_terminal:
                break
            results.append(self.step(obs))
        return results
