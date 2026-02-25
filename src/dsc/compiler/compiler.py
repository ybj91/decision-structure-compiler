"""Decision graph compiler — produces self-contained versioned artifacts.

The compiled artifact contains everything needed for runtime execution:
states, transitions with serialized conditions, action definitions, metadata.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from dsc.models.graph import DecisionGraph
from dsc.models.scenario import Scenario
from dsc.storage.filesystem import FileSystemStorage


class CompiledArtifact:
    """A compiled, self-contained decision graph artifact."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    @property
    def version(self) -> int:
        return self.data["version"]

    @property
    def scenario_id(self) -> str:
        return self.data["scenario_id"]

    def to_json(self) -> str:
        return json.dumps(self.data, indent=2, default=str)

    @classmethod
    def from_json(cls, text: str) -> CompiledArtifact:
        return cls(json.loads(text))


class Compiler:
    """Compiles an optimized DecisionGraph into a self-contained runtime artifact."""

    def __init__(self, storage: FileSystemStorage) -> None:
        self.storage = storage

    def compile(
        self,
        project_id: str,
        scenario: Scenario,
        graph: DecisionGraph,
    ) -> CompiledArtifact:
        """Compile a graph into a versioned artifact.

        The artifact is self-contained: it includes the full graph definition
        plus scenario metadata needed for runtime execution.
        """
        # Determine version
        latest = self.storage.latest_compiled_version(project_id, scenario.id)
        version = (latest or 0) + 1

        # Build artifact
        artifact_data: dict[str, Any] = {
            "format": "dsc-compiled-v1",
            "version": version,
            "scenario_id": scenario.id,
            "scenario_name": scenario.name,
            "compiled_at": datetime.now(timezone.utc).isoformat(),
            "graph": {
                "initial_state": graph.initial_state,
                "terminal_states": graph.terminal_states,
                "states": {
                    name: {
                        "name": state.name,
                        "description": state.description,
                        "metadata": state.metadata,
                    }
                    for name, state in graph.states.items()
                },
                "transitions": [
                    {
                        "from_state": t.from_state,
                        "condition": t.condition.model_dump(),
                        "action": t.action,
                        "action_params": t.action_params,
                        "to_state": t.to_state,
                        "priority": t.priority,
                    }
                    for t in sorted(graph.transitions, key=lambda t: (t.from_state, t.priority))
                ],
            },
            "actions": {
                name: {
                    "name": action.name,
                    "description": action.description,
                    "tool": action.tool,
                    "parameters_schema": action.parameters_schema,
                }
                for name, action in scenario.actions.items()
            },
            "tools": {
                name: {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters_schema": tool.parameters_schema,
                    "returns_schema": tool.returns_schema,
                }
                for name, tool in scenario.tools.items()
            },
            "metadata": {
                "graph_version": graph.version,
                "graph_id": graph.id,
                "state_count": len(graph.states),
                "transition_count": len(graph.transitions),
                "source_traces": graph.metadata.get("source_traces", []),
            },
        }

        artifact = CompiledArtifact(artifact_data)

        # Save to storage
        self.storage.save_compiled(
            project_id, scenario.id, version, artifact.to_json()
        )

        return artifact
