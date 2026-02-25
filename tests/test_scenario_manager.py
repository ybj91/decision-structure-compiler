"""Tests for the Scenario Manager — CRUD and lifecycle."""

from __future__ import annotations

import pytest

from dsc.models.scenario import ScenarioStatus
from dsc.scenario_manager.manager import LifecycleError, ScenarioManager


@pytest.fixture
def manager(storage):
    return ScenarioManager(storage)


class TestProjectCRUD:
    def test_create_and_get(self, manager):
        p = manager.create_project("Test Project", description="desc")
        loaded = manager.get_project(p.id)
        assert loaded.name == "Test Project"
        assert loaded.description == "desc"

    def test_list(self, manager):
        manager.create_project("A")
        manager.create_project("B")
        assert len(manager.list_projects()) == 2

    def test_delete(self, manager):
        p = manager.create_project("Temp")
        manager.delete_project(p.id)
        with pytest.raises(FileNotFoundError):
            manager.get_project(p.id)


class TestScenarioCRUD:
    def test_create_and_get(self, manager):
        p = manager.create_project("P")
        s = manager.create_scenario(p.id, "Customer Support")
        loaded = manager.get_scenario(p.id, s.id)
        assert loaded.name == "Customer Support"
        assert loaded.status == ScenarioStatus.DRAFT

    def test_create_requires_valid_project(self, manager):
        with pytest.raises(FileNotFoundError):
            manager.create_scenario("nonexistent", "S")

    def test_list(self, manager):
        p = manager.create_project("P")
        manager.create_scenario(p.id, "S1")
        manager.create_scenario(p.id, "S2")
        assert len(manager.list_scenarios(p.id)) == 2

    def test_update(self, manager):
        p = manager.create_project("P")
        s = manager.create_scenario(p.id, "S")
        s.context = "Updated context"
        manager.update_scenario(s)
        loaded = manager.get_scenario(p.id, s.id)
        assert loaded.context == "Updated context"

    def test_delete(self, manager):
        p = manager.create_project("P")
        s = manager.create_scenario(p.id, "S")
        manager.delete_scenario(p.id, s.id)
        with pytest.raises(FileNotFoundError):
            manager.get_scenario(p.id, s.id)


class TestLifecycle:
    def test_draft_to_exploration(self, manager):
        p = manager.create_project("P")
        s = manager.create_scenario(p.id, "S")
        s = manager.transition(p.id, s.id, ScenarioStatus.EXPLORATION)
        assert s.status == ScenarioStatus.EXPLORATION

    def test_cannot_skip_stages(self, manager):
        p = manager.create_project("P")
        s = manager.create_scenario(p.id, "S")
        with pytest.raises(LifecycleError, match="Cannot transition"):
            manager.transition(p.id, s.id, ScenarioStatus.COMPILED)

    def test_exploration_to_extraction_needs_traces(self, manager):
        p = manager.create_project("P")
        s = manager.create_scenario(p.id, "S")
        s = manager.transition(p.id, s.id, ScenarioStatus.EXPLORATION)
        with pytest.raises(LifecycleError, match="at least one trace"):
            manager.transition(p.id, s.id, ScenarioStatus.GRAPH_EXTRACTION)

    def test_exploration_to_extraction_with_traces(self, manager):
        p = manager.create_project("P")
        s = manager.create_scenario(p.id, "S")
        s = manager.transition(p.id, s.id, ScenarioStatus.EXPLORATION)
        # Add a trace reference
        s.trace_ids = ["trace1"]
        manager.update_scenario(s)
        s = manager.transition(p.id, s.id, ScenarioStatus.GRAPH_EXTRACTION)
        assert s.status == ScenarioStatus.GRAPH_EXTRACTION

    def test_extraction_to_optimization_needs_graph(self, manager):
        p = manager.create_project("P")
        s = manager.create_scenario(p.id, "S")
        s = manager.transition(p.id, s.id, ScenarioStatus.EXPLORATION)
        s.trace_ids = ["t1"]
        manager.update_scenario(s)
        s = manager.transition(p.id, s.id, ScenarioStatus.GRAPH_EXTRACTION)
        with pytest.raises(LifecycleError, match="extracted graph"):
            manager.transition(p.id, s.id, ScenarioStatus.GRAPH_OPTIMIZATION)

    def test_full_lifecycle(self, manager):
        p = manager.create_project("P")
        s = manager.create_scenario(p.id, "S")

        # Draft → Exploration
        s = manager.transition(p.id, s.id, ScenarioStatus.EXPLORATION)

        # Exploration → Graph Extraction (needs traces)
        s.trace_ids = ["t1"]
        manager.update_scenario(s)
        s = manager.transition(p.id, s.id, ScenarioStatus.GRAPH_EXTRACTION)

        # Graph Extraction → Graph Optimization (needs graph)
        s.graph_version = 1
        manager.update_scenario(s)
        s = manager.transition(p.id, s.id, ScenarioStatus.GRAPH_OPTIMIZATION)

        # Graph Optimization → Compiled (needs graph)
        s = manager.transition(p.id, s.id, ScenarioStatus.COMPILED)

        # Compiled → Production (needs compiled artifact)
        s.compiled_version = 1
        manager.update_scenario(s)
        s = manager.transition(p.id, s.id, ScenarioStatus.PRODUCTION)
        assert s.status == ScenarioStatus.PRODUCTION

    def test_production_can_go_back_to_exploration(self, manager):
        """Support recompilation cycle."""
        p = manager.create_project("P")
        s = manager.create_scenario(p.id, "S")
        s = manager.transition(p.id, s.id, ScenarioStatus.EXPLORATION)
        s.trace_ids = ["t1"]
        manager.update_scenario(s)
        s = manager.transition(p.id, s.id, ScenarioStatus.GRAPH_EXTRACTION)
        s.graph_version = 1
        manager.update_scenario(s)
        s = manager.transition(p.id, s.id, ScenarioStatus.GRAPH_OPTIMIZATION)
        s = manager.transition(p.id, s.id, ScenarioStatus.COMPILED)
        s.compiled_version = 1
        manager.update_scenario(s)
        s = manager.transition(p.id, s.id, ScenarioStatus.PRODUCTION)
        # Go back for recompilation
        s = manager.transition(p.id, s.id, ScenarioStatus.EXPLORATION)
        assert s.status == ScenarioStatus.EXPLORATION
