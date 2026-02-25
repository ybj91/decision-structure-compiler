"""Tests for the deterministic condition evaluator."""

from __future__ import annotations

import pytest

from dsc.models.conditions import (
    AlwaysTrue,
    ConditionGroup,
    FieldCondition,
    LogicOperator,
    Operator,
)
from dsc.runtime.evaluator import evaluate, resolve_field


# ── Field Resolution ────────────────────────────────────────


class TestResolveField:
    def test_simple(self):
        assert resolve_field({"x": 1}, "x") == 1

    def test_nested(self):
        assert resolve_field({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_missing_top_level(self):
        from dsc.runtime.evaluator import _MISSING
        assert resolve_field({"x": 1}, "y") is _MISSING

    def test_missing_nested(self):
        from dsc.runtime.evaluator import _MISSING
        assert resolve_field({"a": {"b": 1}}, "a.c") is _MISSING

    def test_non_dict_intermediate(self):
        from dsc.runtime.evaluator import _MISSING
        assert resolve_field({"a": 42}, "a.b") is _MISSING


# ── AlwaysTrue ──────────────────────────────────────────────


class TestAlwaysTrue:
    def test_always_true(self):
        assert evaluate(AlwaysTrue(), {}) is True
        assert evaluate(AlwaysTrue(), {"anything": "here"}) is True


# ── FieldCondition Operators ────────────────────────────────


class TestFieldConditionEQ:
    def test_string_eq(self):
        c = FieldCondition(field="intent", operator=Operator.EQ, value="refund")
        assert evaluate(c, {"intent": "refund"}) is True
        assert evaluate(c, {"intent": "order"}) is False

    def test_number_eq(self):
        c = FieldCondition(field="count", operator=Operator.EQ, value=5)
        assert evaluate(c, {"count": 5}) is True
        assert evaluate(c, {"count": 6}) is False

    def test_bool_eq(self):
        c = FieldCondition(field="active", operator=Operator.EQ, value=True)
        assert evaluate(c, {"active": True}) is True
        assert evaluate(c, {"active": False}) is False


class TestFieldConditionNE:
    def test_ne(self):
        c = FieldCondition(field="status", operator=Operator.NE, value="closed")
        assert evaluate(c, {"status": "open"}) is True
        assert evaluate(c, {"status": "closed"}) is False


class TestFieldConditionComparisons:
    def test_gt(self):
        c = FieldCondition(field="age", operator=Operator.GT, value=18)
        assert evaluate(c, {"age": 19}) is True
        assert evaluate(c, {"age": 18}) is False
        assert evaluate(c, {"age": 17}) is False

    def test_lt(self):
        c = FieldCondition(field="price", operator=Operator.LT, value=100)
        assert evaluate(c, {"price": 50}) is True
        assert evaluate(c, {"price": 100}) is False

    def test_gte(self):
        c = FieldCondition(field="score", operator=Operator.GTE, value=80)
        assert evaluate(c, {"score": 80}) is True
        assert evaluate(c, {"score": 79}) is False

    def test_lte(self):
        c = FieldCondition(field="days", operator=Operator.LTE, value=30)
        assert evaluate(c, {"days": 30}) is True
        assert evaluate(c, {"days": 31}) is False


class TestFieldConditionMembership:
    def test_in(self):
        c = FieldCondition(field="color", operator=Operator.IN, value=["red", "blue", "green"])
        assert evaluate(c, {"color": "red"}) is True
        assert evaluate(c, {"color": "yellow"}) is False

    def test_not_in(self):
        c = FieldCondition(field="role", operator=Operator.NOT_IN, value=["admin", "root"])
        assert evaluate(c, {"role": "user"}) is True
        assert evaluate(c, {"role": "admin"}) is False


class TestFieldConditionStringOps:
    def test_contains(self):
        c = FieldCondition(field="tags", operator=Operator.CONTAINS, value="urgent")
        assert evaluate(c, {"tags": ["urgent", "billing"]}) is True
        assert evaluate(c, {"tags": ["normal"]}) is False

    def test_contains_string(self):
        c = FieldCondition(field="message", operator=Operator.CONTAINS, value="error")
        assert evaluate(c, {"message": "an error occurred"}) is True
        assert evaluate(c, {"message": "all good"}) is False

    def test_matches(self):
        c = FieldCondition(field="email", operator=Operator.MATCHES, value=r"^[^@]+@[^@]+\.[^@]+$")
        assert evaluate(c, {"email": "user@example.com"}) is True
        assert evaluate(c, {"email": "invalid"}) is False


# ── Missing / Invalid Fields ────────────────────────────────


class TestMissingFields:
    def test_missing_field_returns_false(self):
        c = FieldCondition(field="nonexistent", operator=Operator.EQ, value=42)
        assert evaluate(c, {}) is False

    def test_nested_missing_field(self):
        c = FieldCondition(field="a.b.c", operator=Operator.EQ, value=1)
        assert evaluate(c, {"a": {"x": 1}}) is False

    def test_type_mismatch_returns_false(self):
        c = FieldCondition(field="x", operator=Operator.GT, value=10)
        assert evaluate(c, {"x": "not a number"}) is False


# ── Condition Groups ────────────────────────────────────────


class TestConditionGroupAND:
    def test_all_true(self):
        g = ConditionGroup(
            logic=LogicOperator.AND,
            conditions=[
                FieldCondition(field="a", operator=Operator.EQ, value=1),
                FieldCondition(field="b", operator=Operator.EQ, value=2),
            ],
        )
        assert evaluate(g, {"a": 1, "b": 2}) is True

    def test_one_false(self):
        g = ConditionGroup(
            logic=LogicOperator.AND,
            conditions=[
                FieldCondition(field="a", operator=Operator.EQ, value=1),
                FieldCondition(field="b", operator=Operator.EQ, value=2),
            ],
        )
        assert evaluate(g, {"a": 1, "b": 3}) is False

    def test_short_circuit(self):
        g = ConditionGroup(
            logic=LogicOperator.AND,
            conditions=[
                FieldCondition(field="x", operator=Operator.EQ, value=False),
                FieldCondition(field="y", operator=Operator.EQ, value=1),
            ],
        )
        assert evaluate(g, {"x": True, "y": 1}) is False


class TestConditionGroupOR:
    def test_one_true(self):
        g = ConditionGroup(
            logic=LogicOperator.OR,
            conditions=[
                FieldCondition(field="a", operator=Operator.EQ, value=1),
                FieldCondition(field="b", operator=Operator.EQ, value=2),
            ],
        )
        assert evaluate(g, {"a": 1, "b": 999}) is True

    def test_all_false(self):
        g = ConditionGroup(
            logic=LogicOperator.OR,
            conditions=[
                FieldCondition(field="a", operator=Operator.EQ, value=1),
                FieldCondition(field="b", operator=Operator.EQ, value=2),
            ],
        )
        assert evaluate(g, {"a": 0, "b": 0}) is False


class TestConditionGroupNOT:
    def test_not_true_becomes_false(self):
        g = ConditionGroup(
            logic=LogicOperator.NOT,
            conditions=[FieldCondition(field="blocked", operator=Operator.EQ, value=True)],
        )
        assert evaluate(g, {"blocked": True}) is False

    def test_not_false_becomes_true(self):
        g = ConditionGroup(
            logic=LogicOperator.NOT,
            conditions=[FieldCondition(field="blocked", operator=Operator.EQ, value=True)],
        )
        assert evaluate(g, {"blocked": False}) is True


class TestNestedConditions:
    def test_complex_nested(self):
        """(intent == "refund" AND order_age <= 30) OR is_vip == true"""
        condition = ConditionGroup(
            logic=LogicOperator.OR,
            conditions=[
                ConditionGroup(
                    logic=LogicOperator.AND,
                    conditions=[
                        FieldCondition(field="intent", operator=Operator.EQ, value="refund"),
                        FieldCondition(field="order_age_days", operator=Operator.LTE, value=30),
                    ],
                ),
                FieldCondition(field="is_vip", operator=Operator.EQ, value=True),
            ],
        )
        # Both AND conditions met
        assert evaluate(condition, {"intent": "refund", "order_age_days": 10, "is_vip": False}) is True
        # VIP bypass
        assert evaluate(condition, {"intent": "complaint", "order_age_days": 100, "is_vip": True}) is True
        # Neither
        assert evaluate(condition, {"intent": "refund", "order_age_days": 60, "is_vip": False}) is False

    def test_deeply_nested(self):
        """NOT (a == 1 AND (b == 2 OR c == 3))"""
        condition = ConditionGroup(
            logic=LogicOperator.NOT,
            conditions=[
                ConditionGroup(
                    logic=LogicOperator.AND,
                    conditions=[
                        FieldCondition(field="a", operator=Operator.EQ, value=1),
                        ConditionGroup(
                            logic=LogicOperator.OR,
                            conditions=[
                                FieldCondition(field="b", operator=Operator.EQ, value=2),
                                FieldCondition(field="c", operator=Operator.EQ, value=3),
                            ],
                        ),
                    ],
                )
            ],
        )
        assert evaluate(condition, {"a": 1, "b": 2, "c": 0}) is False  # inner is true, NOT makes false
        assert evaluate(condition, {"a": 0, "b": 2, "c": 3}) is True   # a != 1, so inner false, NOT true

    def test_with_always_true_in_group(self):
        g = ConditionGroup(
            logic=LogicOperator.AND,
            conditions=[
                AlwaysTrue(),
                FieldCondition(field="x", operator=Operator.EQ, value=1),
            ],
        )
        assert evaluate(g, {"x": 1}) is True
        assert evaluate(g, {"x": 2}) is False


class TestNestedFieldPaths:
    def test_dot_path(self):
        c = FieldCondition(field="user.profile.tier", operator=Operator.EQ, value="premium")
        obs = {"user": {"profile": {"tier": "premium"}}}
        assert evaluate(c, obs) is True

    def test_dot_path_mismatch(self):
        c = FieldCondition(field="user.profile.tier", operator=Operator.EQ, value="premium")
        obs = {"user": {"profile": {"tier": "basic"}}}
        assert evaluate(c, obs) is False
