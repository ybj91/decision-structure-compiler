"""JSON filesystem persistence for all DSC entities."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from dsc.models.graph import DecisionGraph
from dsc.models.project import Project
from dsc.models.scenario import Scenario
from dsc.models.trace import ExecutionTrace

T = TypeVar("T", bound=BaseModel)


class FileSystemStorage:
    """Stores all DSC entities as JSON files on the filesystem.

    Directory layout:
        {data_dir}/
          projects/
            {project_id}/
              project.json
              scenarios/
                {scenario_id}/
                  scenario.json
                  traces/
                    {trace_id}.json
                  graphs/
                    v{version}.json
                  compiled/
                    v{version}.json
    """

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)

    # ── helpers ──────────────────────────────────────────────

    def _project_dir(self, project_id: str) -> Path:
        return self.data_dir / "projects" / project_id

    def _project_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "project.json"

    def _scenario_dir(self, project_id: str, scenario_id: str) -> Path:
        return self._project_dir(project_id) / "scenarios" / scenario_id

    def _scenario_path(self, project_id: str, scenario_id: str) -> Path:
        return self._scenario_dir(project_id, scenario_id) / "scenario.json"

    def _trace_path(self, project_id: str, scenario_id: str, trace_id: str) -> Path:
        return self._scenario_dir(project_id, scenario_id) / "traces" / f"{trace_id}.json"

    def _graph_path(self, project_id: str, scenario_id: str, version: int) -> Path:
        return self._scenario_dir(project_id, scenario_id) / "graphs" / f"v{version}.json"

    def _compiled_path(self, project_id: str, scenario_id: str, version: int) -> Path:
        return self._scenario_dir(project_id, scenario_id) / "compiled" / f"v{version}.json"

    def _save(self, path: Path, model: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")

    def _load(self, path: Path, model_cls: type[T]) -> T:
        if not path.exists():
            raise FileNotFoundError(f"Not found: {path}")
        return model_cls.model_validate_json(path.read_text(encoding="utf-8"))

    # ── Projects ─────────────────────────────────────────────

    def save_project(self, project: Project) -> None:
        self._save(self._project_path(project.id), project)

    def load_project(self, project_id: str) -> Project:
        return self._load(self._project_path(project_id), Project)

    def list_projects(self) -> list[Project]:
        projects_dir = self.data_dir / "projects"
        if not projects_dir.exists():
            return []
        results = []
        for p in sorted(projects_dir.iterdir()):
            proj_file = p / "project.json"
            if proj_file.exists():
                results.append(Project.model_validate_json(proj_file.read_text(encoding="utf-8")))
        return results

    def delete_project(self, project_id: str) -> None:
        import shutil

        d = self._project_dir(project_id)
        if d.exists():
            shutil.rmtree(d)

    # ── Scenarios ────────────────────────────────────────────

    def save_scenario(self, scenario: Scenario) -> None:
        self._save(self._scenario_path(scenario.project_id, scenario.id), scenario)

    def load_scenario(self, project_id: str, scenario_id: str) -> Scenario:
        return self._load(self._scenario_path(project_id, scenario_id), Scenario)

    def list_scenarios(self, project_id: str) -> list[Scenario]:
        scenarios_dir = self._project_dir(project_id) / "scenarios"
        if not scenarios_dir.exists():
            return []
        results = []
        for d in sorted(scenarios_dir.iterdir()):
            f = d / "scenario.json"
            if f.exists():
                results.append(Scenario.model_validate_json(f.read_text(encoding="utf-8")))
        return results

    def delete_scenario(self, project_id: str, scenario_id: str) -> None:
        import shutil

        d = self._scenario_dir(project_id, scenario_id)
        if d.exists():
            shutil.rmtree(d)

    # ── Traces ───────────────────────────────────────────────

    def save_trace(self, project_id: str, trace: ExecutionTrace) -> None:
        self._save(
            self._trace_path(project_id, trace.scenario_id, trace.id),
            trace,
        )

    def load_trace(self, project_id: str, scenario_id: str, trace_id: str) -> ExecutionTrace:
        return self._load(self._trace_path(project_id, scenario_id, trace_id), ExecutionTrace)

    def list_traces(self, project_id: str, scenario_id: str) -> list[ExecutionTrace]:
        traces_dir = self._scenario_dir(project_id, scenario_id) / "traces"
        if not traces_dir.exists():
            return []
        results = []
        for f in sorted(traces_dir.glob("*.json")):
            results.append(ExecutionTrace.model_validate_json(f.read_text(encoding="utf-8")))
        return results

    def delete_trace(self, project_id: str, scenario_id: str, trace_id: str) -> None:
        p = self._trace_path(project_id, scenario_id, trace_id)
        if p.exists():
            p.unlink()

    # ── Graphs ───────────────────────────────────────────────

    def save_graph(self, project_id: str, graph: DecisionGraph) -> None:
        self._save(
            self._graph_path(project_id, graph.scenario_id, graph.version),
            graph,
        )

    def load_graph(self, project_id: str, scenario_id: str, version: int) -> DecisionGraph:
        return self._load(self._graph_path(project_id, scenario_id, version), DecisionGraph)

    def latest_graph_version(self, project_id: str, scenario_id: str) -> int | None:
        graphs_dir = self._scenario_dir(project_id, scenario_id) / "graphs"
        if not graphs_dir.exists():
            return None
        versions = []
        for f in graphs_dir.glob("v*.json"):
            try:
                versions.append(int(f.stem[1:]))
            except ValueError:
                continue
        return max(versions) if versions else None

    # ── Compiled Artifacts ───────────────────────────────────

    def save_compiled(self, project_id: str, scenario_id: str, version: int, data: str) -> Path:
        path = self._compiled_path(project_id, scenario_id, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        return path

    def load_compiled(self, project_id: str, scenario_id: str, version: int) -> str:
        path = self._compiled_path(project_id, scenario_id, version)
        if not path.exists():
            raise FileNotFoundError(f"Compiled artifact not found: {path}")
        return path.read_text(encoding="utf-8")

    def load_compiled_from_path(self, path: str | Path) -> str:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Compiled artifact not found: {p}")
        return p.read_text(encoding="utf-8")

    def latest_compiled_version(self, project_id: str, scenario_id: str) -> int | None:
        compiled_dir = self._scenario_dir(project_id, scenario_id) / "compiled"
        if not compiled_dir.exists():
            return None
        versions = []
        for f in compiled_dir.glob("v*.json"):
            try:
                versions.append(int(f.stem[1:]))
            except ValueError:
                continue
        return max(versions) if versions else None
