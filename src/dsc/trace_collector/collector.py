"""Trace storage and retrieval — validates and persists execution traces."""

from __future__ import annotations

import uuid

from dsc.models.trace import ExecutionTrace, TraceSource, TraceStep
from dsc.storage.filesystem import FileSystemStorage


class TraceValidationError(Exception):
    """Raised when a trace fails structural validation."""


class TraceCollector:
    """Collects, validates, stores, and retrieves execution traces."""

    def __init__(self, storage: FileSystemStorage) -> None:
        self.storage = storage

    def add_trace(
        self,
        project_id: str,
        scenario_id: str,
        trace: ExecutionTrace,
    ) -> ExecutionTrace:
        """Validate and store a trace, returning it with its assigned ID."""
        self._validate_trace(trace)
        self.storage.save_trace(project_id, trace)
        return trace

    def create_trace(
        self,
        project_id: str,
        scenario_id: str,
        initial_state: str,
        steps: list[TraceStep],
        source: TraceSource = TraceSource.USER,
        metadata: dict | None = None,
    ) -> ExecutionTrace:
        """Create and store a new trace."""
        trace = ExecutionTrace(
            id=uuid.uuid4().hex[:12],
            scenario_id=scenario_id,
            source=source,
            initial_state=initial_state,
            steps=steps,
            metadata=metadata or {},
        )
        return self.add_trace(project_id, scenario_id, trace)

    def get_trace(self, project_id: str, scenario_id: str, trace_id: str) -> ExecutionTrace:
        return self.storage.load_trace(project_id, scenario_id, trace_id)

    def list_traces(self, project_id: str, scenario_id: str) -> list[ExecutionTrace]:
        return self.storage.list_traces(project_id, scenario_id)

    def delete_trace(self, project_id: str, scenario_id: str, trace_id: str) -> None:
        self.storage.delete_trace(project_id, scenario_id, trace_id)

    def _validate_trace(self, trace: ExecutionTrace) -> None:
        """Validate structural consistency of a trace."""
        if not trace.steps:
            raise TraceValidationError("Trace must have at least one step")

        # First step's state must match initial_state
        if trace.steps[0].state != trace.initial_state:
            raise TraceValidationError(
                f"First step state '{trace.steps[0].state}' does not match "
                f"initial_state '{trace.initial_state}'"
            )

        # Each step's next_state must match the following step's state
        for i in range(len(trace.steps) - 1):
            current_next = trace.steps[i].next_state
            following_state = trace.steps[i + 1].state
            if current_next != following_state:
                raise TraceValidationError(
                    f"Step {i} next_state '{current_next}' does not match "
                    f"step {i + 1} state '{following_state}'"
                )
