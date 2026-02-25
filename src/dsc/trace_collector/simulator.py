"""LLM-based trace simulation — uses Claude to generate execution traces."""

from __future__ import annotations

import uuid
from typing import Any

from dsc.llm.client import LLMClient
from dsc.llm.prompts import trace_simulation_prompt
from dsc.models.scenario import Scenario
from dsc.models.trace import ExecutionTrace, TraceSource, TraceStep


class TraceSimulator:
    """Simulates execution traces using an LLM.

    Given a scenario definition and test input, asks Claude to simulate
    a realistic execution trace step by step.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    def simulate(
        self,
        scenario: Scenario,
        test_input: dict[str, Any],
        metadata: dict | None = None,
    ) -> ExecutionTrace:
        """Simulate a trace for the given scenario and test input.

        Returns a validated ExecutionTrace with source=LLM.
        """
        system, messages, tool_name, tool_schema = trace_simulation_prompt(
            scenario, test_input,
        )

        result = self.llm.structured_request(
            system=system,
            messages=messages,
            tool_name=tool_name,
            tool_schema=tool_schema,
        )

        steps = [
            TraceStep(
                state=step["state"],
                observation=step.get("observation", {}),
                decision=step.get("decision", ""),
                action=step["action"],
                action_params=step.get("action_params", {}),
                tool_result=step.get("tool_result"),
                next_state=step["next_state"],
            )
            for step in result["steps"]
        ]

        trace = ExecutionTrace(
            id=uuid.uuid4().hex[:12],
            scenario_id=scenario.id,
            source=TraceSource.LLM,
            initial_state=result["initial_state"],
            steps=steps,
            metadata={
                "test_input": test_input,
                **(metadata or {}),
            },
        )

        return trace
