"""Deterministic condition evaluator.

Evaluates ConditionExpr AST nodes against observation dictionaries.
This is the hot path at runtime — pure functions, no side effects.
"""

from __future__ import annotations

import re
from typing import Any

from dsc.models.conditions import (
    AlwaysTrue,
    ConditionExpr,
    ConditionGroup,
    FieldCondition,
    LogicOperator,
    Operator,
)

# Sentinel for missing fields
_MISSING = object()


def resolve_field(observation: dict, field_path: str) -> Any:
    """Resolve a dot-separated field path in an observation dict.

    Returns _MISSING if the field doesn't exist at any level.

    Examples:
        resolve_field({"user": {"intent": "refund"}}, "user.intent") → "refund"
        resolve_field({"x": 1}, "y") → _MISSING
    """
    current = observation
    for part in field_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def evaluate_field_condition(condition: FieldCondition, observation: dict) -> bool:
    """Evaluate a single field condition against an observation."""
    value = resolve_field(observation, condition.field)
    if value is _MISSING:
        return False

    expected = condition.value
    op = condition.operator

    try:
        if op == Operator.EQ:
            return value == expected
        elif op == Operator.NE:
            return value != expected
        elif op == Operator.GT:
            return value > expected
        elif op == Operator.LT:
            return value < expected
        elif op == Operator.GTE:
            return value >= expected
        elif op == Operator.LTE:
            return value <= expected
        elif op == Operator.IN:
            return value in expected
        elif op == Operator.NOT_IN:
            return value not in expected
        elif op == Operator.CONTAINS:
            return expected in value
        elif op == Operator.MATCHES:
            return bool(re.search(expected, str(value)))
    except (TypeError, ValueError):
        return False

    return False


def evaluate(condition: ConditionExpr, observation: dict) -> bool:
    """Evaluate any condition expression against an observation.

    This is the main entry point for condition evaluation.
    """
    if isinstance(condition, AlwaysTrue):
        return True

    if isinstance(condition, FieldCondition):
        return evaluate_field_condition(condition, observation)

    if isinstance(condition, ConditionGroup):
        return _evaluate_group(condition, observation)

    raise TypeError(f"Unknown condition type: {type(condition)}")


def _evaluate_group(group: ConditionGroup, observation: dict) -> bool:
    """Evaluate a compound condition group."""
    if group.logic == LogicOperator.AND:
        return all(evaluate(c, observation) for c in group.conditions)
    elif group.logic == LogicOperator.OR:
        return any(evaluate(c, observation) for c in group.conditions)
    elif group.logic == LogicOperator.NOT:
        if len(group.conditions) != 1:
            raise ValueError("NOT condition must have exactly one sub-condition")
        return not evaluate(group.conditions[0], observation)
    raise ValueError(f"Unknown logic operator: {group.logic}")
