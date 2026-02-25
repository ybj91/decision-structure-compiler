"""Scenario lifecycle management — CRUD operations and state transitions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from dsc.models.project import Project
from dsc.models.scenario import VALID_TRANSITIONS, Scenario, ScenarioStatus
from dsc.storage.filesystem import FileSystemStorage


class LifecycleError(Exception):
    """Raised when an invalid scenario lifecycle transition is attempted."""


class ScenarioManager:
    """Manages projects and scenarios with lifecycle enforcement."""

    def __init__(self, storage: FileSystemStorage) -> None:
        self.storage = storage

    # ── Projects ─────────────────────────────────────────────

    def create_project(self, name: str, description: str = "") -> Project:
        project = Project(
            id=uuid.uuid4().hex[:12],
            name=name,
            description=description,
        )
        self.storage.save_project(project)
        return project

    def get_project(self, project_id: str) -> Project:
        return self.storage.load_project(project_id)

    def list_projects(self) -> list[Project]:
        return self.storage.list_projects()

    def delete_project(self, project_id: str) -> None:
        self.storage.delete_project(project_id)

    # ── Scenarios ────────────────────────────────────────────

    def create_scenario(self, project_id: str, name: str, **kwargs) -> Scenario:
        # Verify project exists
        self.storage.load_project(project_id)
        scenario = Scenario(
            id=uuid.uuid4().hex[:12],
            project_id=project_id,
            name=name,
            **kwargs,
        )
        self.storage.save_scenario(scenario)
        return scenario

    def get_scenario(self, project_id: str, scenario_id: str) -> Scenario:
        return self.storage.load_scenario(project_id, scenario_id)

    def list_scenarios(self, project_id: str) -> list[Scenario]:
        return self.storage.list_scenarios(project_id)

    def update_scenario(self, scenario: Scenario) -> Scenario:
        scenario.updated_at = datetime.now(timezone.utc)
        self.storage.save_scenario(scenario)
        return scenario

    def delete_scenario(self, project_id: str, scenario_id: str) -> None:
        self.storage.delete_scenario(project_id, scenario_id)

    # ── Lifecycle ────────────────────────────────────────────

    def transition(self, project_id: str, scenario_id: str, target: ScenarioStatus) -> Scenario:
        """Advance a scenario to a new lifecycle stage.

        Validates that the transition is allowed and that preconditions are met.
        """
        scenario = self.storage.load_scenario(project_id, scenario_id)
        current = scenario.status
        allowed = VALID_TRANSITIONS.get(current, [])

        if target not in allowed:
            raise LifecycleError(
                f"Cannot transition from {current.value} to {target.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )

        self._check_preconditions(scenario, target)

        scenario.status = target
        scenario.updated_at = datetime.now(timezone.utc)
        self.storage.save_scenario(scenario)
        return scenario

    def _check_preconditions(self, scenario: Scenario, target: ScenarioStatus) -> None:
        """Check that preconditions are met for a lifecycle transition."""
        if target == ScenarioStatus.GRAPH_EXTRACTION:
            if not scenario.trace_ids:
                raise LifecycleError(
                    "Cannot enter Graph Extraction: scenario must have at least one trace"
                )

        elif target == ScenarioStatus.GRAPH_OPTIMIZATION:
            if scenario.graph_version is None:
                raise LifecycleError(
                    "Cannot enter Graph Optimization: scenario must have an extracted graph"
                )

        elif target == ScenarioStatus.COMPILED:
            if scenario.graph_version is None:
                raise LifecycleError(
                    "Cannot compile: scenario must have an optimized graph"
                )

        elif target == ScenarioStatus.PRODUCTION:
            if scenario.compiled_version is None:
                raise LifecycleError(
                    "Cannot enter Production: scenario must have a compiled artifact"
                )
