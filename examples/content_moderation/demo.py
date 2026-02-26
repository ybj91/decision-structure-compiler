"""Content Moderation Pipeline -- demo showing multi-stage filtering.

This scenario routes user-submitted content through toxicity checks,
policy checks, and spam checks, each with threshold-based routing.

Run:
    python examples/content_moderation/demo.py
"""

from pathlib import Path

from dsc.compiler.compiler import CompiledArtifact
from dsc.runtime.engine import RuntimeConfig, RuntimeEngine

EXAMPLE_DIR = Path(__file__).parent


def run_scenario(name: str, artifact: CompiledArtifact, observations: list[dict]):
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")

    def on_action(action: str, params: dict):
        detail = f" {params}" if params else ""
        print(f"    -> {action}{detail}")
        return {"status": "ok"}

    config = RuntimeConfig(action_handler=on_action)
    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()

    for obs in observations:
        if engine.is_terminal:
            break
        print(f"\n  [{engine.current_state}]")
        print(f"  Observation: {obs}")
        result = engine.step(obs)
        print(f"  => {result.to_state}")

    print(f"\n  FINAL STATE: {engine.current_state} ({engine.step_count} steps)")
    return engine.current_state


def main():
    artifact = CompiledArtifact.from_json(
        (EXAMPLE_DIR / "compiled_artifact.json").read_text()
    )
    print(f"Loaded: {artifact.data['scenario_name']}")

    # ── Clean content passes all checks ──────────────────────
    run_scenario(
        "CLEAN CONTENT - trusted author, no issues",
        artifact,
        [
            {"content_type": "text", "content": "Great article about gardening!"},
            {"toxicity_score": 0.05},
            {"policy_violations": 0},
            {"spam_score": 0.1, "author_reputation": 85},
        ],
    )

    # ── Toxic content gets rejected immediately ──────────────
    run_scenario(
        "TOXIC CONTENT - rejected at toxicity check",
        artifact,
        [
            {"content_type": "text", "content": "extremely offensive content..."},
            {"toxicity_score": 0.95},
        ],
    )

    # ── Borderline toxicity goes to human review ─────────────
    run_scenario(
        "BORDERLINE CONTENT - held for manual review",
        artifact,
        [
            {"content_type": "text", "content": "somewhat aggressive debate comment"},
            {"toxicity_score": 0.65},
        ],
    )

    # ── Spam from low-reputation author ──────────────────────
    run_scenario(
        "SPAM - new author promoting products",
        artifact,
        [
            {"content_type": "text", "content": "Buy cheap watches at ..."},
            {"toxicity_score": 0.1},
            {"policy_violations": 0},
            {"spam_score": 0.85, "author_reputation": 10},
        ],
    )

    # ── Clean content but new author, manual review ──────────
    run_scenario(
        "NEW AUTHOR - clean content, low reputation -> review",
        artifact,
        [
            {"content_type": "text", "content": "My first post here!"},
            {"toxicity_score": 0.02},
            {"policy_violations": 0},
            {"spam_score": 0.15, "author_reputation": 5},
        ],
    )

    # ── Image content goes straight to manual review ─────────
    run_scenario(
        "IMAGE UPLOAD - media always requires human review",
        artifact,
        [
            {"content_type": "image", "filename": "photo.jpg"},
        ],
    )

    # ── Policy violation ─────────────────────────────────────
    run_scenario(
        "POLICY VIOLATION - content breaks community guidelines",
        artifact,
        [
            {"content_type": "text", "content": "content with policy issues"},
            {"toxicity_score": 0.2},
            {"policy_violations": 3},
        ],
    )


if __name__ == "__main__":
    main()
