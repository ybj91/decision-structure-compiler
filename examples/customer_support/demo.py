"""Customer Support Routing -- end-to-end demo.

This script demonstrates the full DSC pipeline without requiring an LLM.
It uses pre-built traces and manually constructs the graph to show
how all the pieces fit together.

Run:
    python examples/customer_support/demo.py
"""

from pathlib import Path

from dsc.compiler.compiler import CompiledArtifact
from dsc.runtime.engine import RuntimeConfig, RuntimeEngine

EXAMPLE_DIR = Path(__file__).parent


def main():
    # ── Load the pre-built compiled artifact ─────────────────
    artifact_path = EXAMPLE_DIR / "compiled_artifact.json"
    artifact = CompiledArtifact.from_json(artifact_path.read_text())

    print(f"Loaded: {artifact.data['scenario_name']} v{artifact.version}")
    print(f"States: {artifact.data['metadata']['state_count']}, "
          f"Transitions: {artifact.data['metadata']['transition_count']}")
    print()

    # ── Set up an action handler to see what's happening ─────
    def on_action(action: str, params: dict):
        print(f"    -> Action: {action}", end="")
        if params:
            print(f" {params}", end="")
        print()
        return {"status": "ok"}

    config = RuntimeConfig(action_handler=on_action)

    # ── Scenario 1: Happy path refund ────────────────────────
    print("=" * 60)
    print("SCENARIO 1: Customer wants a refund (eligible)")
    print("=" * 60)

    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()

    observations = [
        {"intent": "refund", "message": "I want to return my order"},
        {"order_age_days": 12, "order_amount": 89.99, "item_condition": "unopened"},
        {"refund_confirmed": True},
    ]

    for obs in observations:
        print(f"\n  State: {engine.current_state}")
        print(f"  Observation: {obs}")
        result = engine.step(obs)
        print(f"  -> New state: {result.to_state}")

    print(f"\n  RESULT: {'Terminal' if engine.is_terminal else 'Running'} "
          f"({engine.step_count} steps)")

    # ── Scenario 2: Refund denied, customer escalates ────────
    print()
    print("=" * 60)
    print("SCENARIO 2: Refund denied (old order), customer escalates")
    print("=" * 60)

    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()

    observations = [
        {"intent": "refund", "message": "I need my money back"},
        {"order_age_days": 45, "order_amount": 249.00, "item_condition": "used",
         "customer_tier": "standard"},
        {"customer_satisfied": False},
    ]

    for obs in observations:
        print(f"\n  State: {engine.current_state}")
        print(f"  Observation: {obs}")
        result = engine.step(obs)
        print(f"  -> New state: {result.to_state}")

    print(f"\n  RESULT: {'Terminal' if engine.is_terminal else 'Running'} "
          f"({engine.step_count} steps)")

    # ── Scenario 3: VIP gets courtesy refund ─────────────────
    print()
    print("=" * 60)
    print("SCENARIO 3: Premium customer gets courtesy refund")
    print("=" * 60)

    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()

    observations = [
        {"intent": "refund", "message": "I'd like to return this"},
        {"order_age_days": 55, "order_amount": 320.00, "item_condition": "used",
         "customer_tier": "premium"},
        {"refund_confirmed": True},
    ]

    for obs in observations:
        print(f"\n  State: {engine.current_state}")
        print(f"  Observation: {obs}")
        result = engine.step(obs)
        print(f"  -> New state: {result.to_state}")

    print(f"\n  RESULT: {'Terminal' if engine.is_terminal else 'Running'} "
          f"({engine.step_count} steps)")

    # ── Scenario 4: General inquiry ──────────────────────────
    print()
    print("=" * 60)
    print("SCENARIO 4: Customer asks a question")
    print("=" * 60)

    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()

    observations = [
        {"intent": "question", "message": "When will my order arrive?"},
        {"customer_satisfied": True},
    ]

    for obs in observations:
        print(f"\n  State: {engine.current_state}")
        print(f"  Observation: {obs}")
        result = engine.step(obs)
        print(f"  -> New state: {result.to_state}")

    print(f"\n  RESULT: {'Terminal' if engine.is_terminal else 'Running'} "
          f"({engine.step_count} steps)")

    # ── Scenario 5: Unknown intent hits default ──────────────
    print()
    print("=" * 60)
    print("SCENARIO 5: Unknown intent (falls through to default)")
    print("=" * 60)

    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()

    observations = [
        {"intent": "something_unexpected", "message": "asdlfkjasdf"},
        {"customer_satisfied": True},
    ]

    for obs in observations:
        print(f"\n  State: {engine.current_state}")
        print(f"  Observation: {obs}")
        result = engine.step(obs)
        print(f"  -> New state: {result.to_state}")

    print(f"\n  RESULT: {'Terminal' if engine.is_terminal else 'Running'} "
          f"({engine.step_count} steps)")


if __name__ == "__main__":
    main()
