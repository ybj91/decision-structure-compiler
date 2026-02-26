"""Programmatic API demo -- build a scenario, graph, and runtime from Python.

This example shows how to use DSC as a library without the CLI or LLM.
You define the scenario, manually construct the decision graph, compile it,
and run it -- all in code.

Use case: a simple order fulfillment pipeline.

Run:
    python examples/programmatic_api/build_and_run.py
"""

import tempfile
from pathlib import Path

from dsc.compiler.compiler import Compiler
from dsc.graph_optimizer.optimizer import GraphOptimizer
from dsc.models.conditions import (
    AlwaysTrue,
    ConditionGroup,
    FieldCondition,
    LogicOperator,
    Operator,
)
from dsc.models.graph import DecisionGraph, StateDefinition, Transition
from dsc.models.project import Project
from dsc.models.scenario import ActionDefinition, ObservationField, ObservationSchema, Scenario
from dsc.runtime.engine import RuntimeConfig, RuntimeEngine
from dsc.storage.filesystem import FileSystemStorage


def main():
    # ── 1. Set up storage ────────────────────────────────────
    data_dir = Path(tempfile.mkdtemp())
    storage = FileSystemStorage(data_dir)

    # ── 2. Create a project and scenario ─────────────────────
    project = Project(id="order-proj", name="E-Commerce Orders")
    storage.save_project(project)

    scenario = Scenario(
        id="order-fulfillment",
        project_id=project.id,
        name="Order Fulfillment",
        context="Process incoming orders: validate payment, check inventory, ship or cancel.",
        observation_schema=ObservationSchema(fields={
            "payment_status": ObservationField(type="string", description="Payment validation result"),
            "inventory_available": ObservationField(type="boolean", description="Whether items are in stock"),
            "shipping_method": ObservationField(type="string", description="Selected shipping method"),
        }),
        actions={
            "validate_payment": ActionDefinition(name="validate_payment", description="Check payment method"),
            "check_inventory": ActionDefinition(name="check_inventory", description="Verify stock levels"),
            "allocate_inventory": ActionDefinition(name="allocate_inventory", description="Reserve items"),
            "create_shipment": ActionDefinition(name="create_shipment", description="Generate shipping label"),
            "cancel_order": ActionDefinition(name="cancel_order", description="Cancel and refund"),
            "notify_customer": ActionDefinition(name="notify_customer", description="Send status update"),
        },
    )
    storage.save_scenario(scenario)

    print("Created project and scenario")
    print(f"  Project:  {project.name} ({project.id})")
    print(f"  Scenario: {scenario.name} ({scenario.id})")

    # ── 3. Build the decision graph manually ─────────────────
    #
    #  order_received
    #       |
    #       v
    #  payment_validation --[failed]--> cancelled
    #       |                              ^
    #    [success]                         |
    #       v                              |
    #  inventory_check ---[no stock]-------+
    #       |
    #    [in stock]
    #       v
    #  shipping
    #       |
    #       v
    #  completed

    graph = DecisionGraph(
        id="graph-order-001",
        scenario_id=scenario.id,
        version=1,
        states={
            "order_received": StateDefinition(name="order_received", description="New order placed"),
            "payment_validation": StateDefinition(name="payment_validation", description="Validating payment"),
            "inventory_check": StateDefinition(name="inventory_check", description="Checking stock"),
            "shipping": StateDefinition(name="shipping", description="Preparing shipment"),
            "completed": StateDefinition(name="completed", description="Order fulfilled"),
            "cancelled": StateDefinition(name="cancelled", description="Order cancelled"),
        },
        transitions=[
            # order_received -> payment_validation (always)
            Transition(
                from_state="order_received",
                condition=AlwaysTrue(),
                action="validate_payment",
                to_state="payment_validation",
                priority=0,
            ),
            # payment OK -> inventory check
            Transition(
                from_state="payment_validation",
                condition=FieldCondition(field="payment_status", operator=Operator.EQ, value="approved"),
                action="check_inventory",
                to_state="inventory_check",
                priority=0,
            ),
            # payment failed -> cancel
            Transition(
                from_state="payment_validation",
                condition=FieldCondition(field="payment_status", operator=Operator.EQ, value="declined"),
                action="cancel_order",
                action_params={"reason": "payment_declined"},
                to_state="cancelled",
                priority=1,
            ),
            # payment pending -> stay (retry)
            Transition(
                from_state="payment_validation",
                condition=FieldCondition(field="payment_status", operator=Operator.EQ, value="pending"),
                action="notify_customer",
                action_params={"message": "Payment is still processing..."},
                to_state="payment_validation",
                priority=2,
            ),
            # in stock -> shipping
            Transition(
                from_state="inventory_check",
                condition=FieldCondition(field="inventory_available", operator=Operator.EQ, value=True),
                action="allocate_inventory",
                to_state="shipping",
                priority=0,
            ),
            # out of stock -> cancel
            Transition(
                from_state="inventory_check",
                condition=FieldCondition(field="inventory_available", operator=Operator.EQ, value=False),
                action="cancel_order",
                action_params={"reason": "out_of_stock"},
                to_state="cancelled",
                priority=1,
            ),
            # shipping -> completed (express)
            Transition(
                from_state="shipping",
                condition=FieldCondition(field="shipping_method", operator=Operator.EQ, value="express"),
                action="create_shipment",
                action_params={"priority": "high"},
                to_state="completed",
                priority=0,
            ),
            # shipping -> completed (standard, default)
            Transition(
                from_state="shipping",
                condition=AlwaysTrue(),
                action="create_shipment",
                action_params={"priority": "normal"},
                to_state="completed",
                priority=100,
            ),
        ],
        initial_state="order_received",
        terminal_states=["completed", "cancelled"],
    )

    # ── 4. Optimize ──────────────────────────────────────────
    optimizer = GraphOptimizer()
    optimized_graph, report = optimizer.optimize(graph)
    optimized_graph.version = 2  # bump version after optimization

    print(f"\nOptimization:")
    print(f"  States:      {report.original_state_count} -> {report.final_state_count}")
    print(f"  Transitions: {report.original_transition_count} -> {report.final_transition_count}")
    print(f"  Removed:     {report.states_removed or '(none)'}")
    print(f"  Conflicts:   {len(report.conflicts)}")

    storage.save_graph(project.id, optimized_graph)

    # ── 5. Compile ───────────────────────────────────────────
    compiler = Compiler(storage)
    artifact = compiler.compile(project.id, scenario, optimized_graph)
    print(f"\nCompiled artifact v{artifact.version}")

    # ── 6. Run scenarios ─────────────────────────────────────
    actions_log = []

    def action_handler(action, params):
        actions_log.append((action, params))
        return {"status": "ok"}

    config = RuntimeConfig(action_handler=action_handler)

    # --- Happy path: payment approved, in stock, express shipping
    print("\n" + "=" * 60)
    print("  ORDER 1: Successful express order")
    print("=" * 60)

    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()
    actions_log.clear()

    steps = [
        {"order_id": "ORD-001"},                       # -> payment_validation
        {"payment_status": "approved"},                 # -> inventory_check
        {"inventory_available": True},                  # -> shipping
        {"shipping_method": "express"},                 # -> completed
    ]

    for obs in steps:
        result = engine.step(obs)
        print(f"  {result.from_state} -> {result.to_state}  (action: {result.action})")

    print(f"  Final: {engine.current_state} | Actions: {[a for a, _ in actions_log]}")

    # --- Payment declined
    print("\n" + "=" * 60)
    print("  ORDER 2: Payment declined")
    print("=" * 60)

    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()
    actions_log.clear()

    steps = [
        {"order_id": "ORD-002"},
        {"payment_status": "declined"},
    ]

    for obs in steps:
        result = engine.step(obs)
        print(f"  {result.from_state} -> {result.to_state}  (action: {result.action})")

    print(f"  Final: {engine.current_state} | Actions: {[a for a, _ in actions_log]}")

    # --- Out of stock
    print("\n" + "=" * 60)
    print("  ORDER 3: Out of stock")
    print("=" * 60)

    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()
    actions_log.clear()

    steps = [
        {"order_id": "ORD-003"},
        {"payment_status": "approved"},
        {"inventory_available": False},
    ]

    for obs in steps:
        result = engine.step(obs)
        print(f"  {result.from_state} -> {result.to_state}  (action: {result.action})")

    print(f"  Final: {engine.current_state} | Actions: {[a for a, _ in actions_log]}")

    # --- Payment pending -> retry -> approved
    print("\n" + "=" * 60)
    print("  ORDER 4: Payment pending then approved (retry loop)")
    print("=" * 60)

    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()
    actions_log.clear()

    steps = [
        {"order_id": "ORD-004"},
        {"payment_status": "pending"},       # stays in payment_validation
        {"payment_status": "pending"},       # still pending
        {"payment_status": "approved"},      # finally approved
        {"inventory_available": True},
        {"shipping_method": "standard"},
    ]

    for obs in steps:
        if engine.is_terminal:
            break
        result = engine.step(obs)
        print(f"  {result.from_state} -> {result.to_state}  (action: {result.action})")

    print(f"  Final: {engine.current_state} | Actions: {[a for a, _ in actions_log]}")


if __name__ == "__main__":
    main()
