"""Typer CLI for the Decision Structure Compiler."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from dsc.compiler.compiler import CompiledArtifact, Compiler
from dsc.graph_extractor.extractor import GraphExtractor
from dsc.graph_optimizer.optimizer import GraphOptimizer
from dsc.llm.client import LLMClient
from dsc.models.scenario import ScenarioStatus
from dsc.models.trace import ExecutionTrace
from dsc.runtime.engine import RuntimeConfig, RuntimeEngine, UnmatchedStateError
from dsc.scenario_manager.manager import LifecycleError, ScenarioManager
from dsc.storage.filesystem import FileSystemStorage
from dsc.trace_collector.collector import TraceCollector, TraceValidationError
from dsc.trace_collector.simulator import TraceSimulator

app = typer.Typer(name="dsc", help="Decision Structure Compiler")
console = Console()

# Default data directory
DEFAULT_DATA_DIR = Path(".dsc_data")


def _get_storage(data_dir: Path = DEFAULT_DATA_DIR) -> FileSystemStorage:
    return FileSystemStorage(data_dir)


def _get_manager(data_dir: Path = DEFAULT_DATA_DIR) -> ScenarioManager:
    return ScenarioManager(_get_storage(data_dir))


# ── Project Commands ─────────────────────────────────────────

project_app = typer.Typer(help="Project management")
app.add_typer(project_app, name="project")


@app.command()
def init(name: str, description: str = "") -> None:
    """Create a new project."""
    manager = _get_manager()
    project = manager.create_project(name, description)
    console.print(f"[green]Created project:[/green] {project.name} (id: {project.id})")


@project_app.command("list")
def project_list() -> None:
    """List all projects."""
    manager = _get_manager()
    projects = manager.list_projects()
    if not projects:
        console.print("[dim]No projects found.[/dim]")
        return

    table = Table(title="Projects")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Description")

    for p in projects:
        table.add_row(p.id, p.name, p.description)

    console.print(table)


# ── Scenario Commands ────────────────────────────────────────

scenario_app = typer.Typer(help="Scenario management")
app.add_typer(scenario_app, name="scenario")


@scenario_app.command("create")
def scenario_create(
    project_id: str,
    name: str,
    context: str = "",
) -> None:
    """Create a new scenario within a project."""
    manager = _get_manager()
    try:
        scenario = manager.create_scenario(project_id, name, context=context)
        console.print(f"[green]Created scenario:[/green] {scenario.name} (id: {scenario.id})")
    except FileNotFoundError:
        console.print(f"[red]Project not found:[/red] {project_id}")
        raise typer.Exit(1)


@scenario_app.command("list")
def scenario_list(project_id: str) -> None:
    """List all scenarios in a project."""
    manager = _get_manager()
    scenarios = manager.list_scenarios(project_id)
    if not scenarios:
        console.print("[dim]No scenarios found.[/dim]")
        return

    table = Table(title="Scenarios")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Status", style="yellow")
    table.add_column("Traces")
    table.add_column("Graph Ver.")

    for s in scenarios:
        table.add_row(
            s.id, s.name, s.status.value,
            str(len(s.trace_ids)),
            str(s.graph_version or "-"),
        )

    console.print(table)


@scenario_app.command("status")
def scenario_status(project_id: str, scenario_id: str) -> None:
    """Show detailed scenario status."""
    manager = _get_manager()
    try:
        s = manager.get_scenario(project_id, scenario_id)
    except FileNotFoundError:
        console.print("[red]Scenario not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]{s.name}[/bold] ({s.id})")
    console.print(f"  Status:    [yellow]{s.status.value}[/yellow]")
    console.print(f"  Traces:    {len(s.trace_ids)}")
    console.print(f"  Graph:     v{s.graph_version or '-'}")
    console.print(f"  Compiled:  v{s.compiled_version or '-'}")
    console.print(f"  Context:   {s.context[:80] or '(none)'}...")


@scenario_app.command("advance")
def scenario_advance(
    project_id: str,
    scenario_id: str,
    target: str,
) -> None:
    """Advance scenario to the next lifecycle stage."""
    manager = _get_manager()
    try:
        target_status = ScenarioStatus(target)
    except ValueError:
        console.print(f"[red]Invalid status:[/red] {target}")
        console.print(f"Valid: {[s.value for s in ScenarioStatus]}")
        raise typer.Exit(1)

    try:
        scenario = manager.transition(project_id, scenario_id, target_status)
        console.print(f"[green]Scenario advanced to:[/green] {scenario.status.value}")
    except LifecycleError as e:
        console.print(f"[red]Lifecycle error:[/red] {e}")
        raise typer.Exit(1)


# ── Trace Commands ───────────────────────────────────────────

trace_app = typer.Typer(help="Trace management")
app.add_typer(trace_app, name="trace")


@trace_app.command("add")
def trace_add(
    project_id: str,
    scenario_id: str,
    file: Path,
) -> None:
    """Add a user-provided trace from a JSON file."""
    storage = _get_storage()
    collector = TraceCollector(storage)

    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        trace = ExecutionTrace.model_validate(data)
        trace.scenario_id = scenario_id
        result = collector.add_trace(project_id, scenario_id, trace)

        # Update scenario's trace list
        manager = ScenarioManager(storage)
        scenario = manager.get_scenario(project_id, scenario_id)
        if result.id not in scenario.trace_ids:
            scenario.trace_ids.append(result.id)
            manager.update_scenario(scenario)

        console.print(f"[green]Added trace:[/green] {result.id}")
    except TraceValidationError as e:
        console.print(f"[red]Validation error:[/red] {e}")
        raise typer.Exit(1)
    except FileNotFoundError:
        console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(1)


@trace_app.command("simulate")
def trace_simulate(
    project_id: str,
    scenario_id: str,
    input_file: Path,
    model: str = "claude-sonnet-4-20250514",
) -> None:
    """Simulate a trace using an LLM."""
    storage = _get_storage()
    manager = ScenarioManager(storage)

    try:
        scenario = manager.get_scenario(project_id, scenario_id)
    except FileNotFoundError:
        console.print("[red]Scenario not found.[/red]")
        raise typer.Exit(1)

    test_input = json.loads(input_file.read_text(encoding="utf-8"))

    llm = LLMClient(model=model)
    simulator = TraceSimulator(llm)

    console.print("[dim]Simulating trace...[/dim]")
    trace = simulator.simulate(scenario, test_input)

    # Save trace
    collector = TraceCollector(storage)
    collector.add_trace(project_id, scenario_id, trace)

    # Update scenario
    if trace.id not in scenario.trace_ids:
        scenario.trace_ids.append(trace.id)
        manager.update_scenario(scenario)

    console.print(f"[green]Simulated trace:[/green] {trace.id} ({len(trace.steps)} steps)")


@trace_app.command("list")
def trace_list(project_id: str, scenario_id: str) -> None:
    """List traces for a scenario."""
    storage = _get_storage()
    collector = TraceCollector(storage)
    traces = collector.list_traces(project_id, scenario_id)

    if not traces:
        console.print("[dim]No traces found.[/dim]")
        return

    table = Table(title="Traces")
    table.add_column("ID", style="cyan")
    table.add_column("Source")
    table.add_column("Initial State")
    table.add_column("Steps")

    for t in traces:
        table.add_row(t.id, t.source.value, t.initial_state, str(len(t.steps)))

    console.print(table)


# ── Pipeline Commands ────────────────────────────────────────


@app.command()
def extract(
    project_id: str,
    scenario_id: str,
    model: str = "claude-sonnet-4-20250514",
) -> None:
    """Run graph extraction on a scenario's traces."""
    storage = _get_storage()
    manager = ScenarioManager(storage)

    try:
        scenario = manager.get_scenario(project_id, scenario_id)
    except FileNotFoundError:
        console.print("[red]Scenario not found.[/red]")
        raise typer.Exit(1)

    collector = TraceCollector(storage)
    traces = collector.list_traces(project_id, scenario_id)

    if not traces:
        console.print("[red]No traces found. Add traces before extracting.[/red]")
        raise typer.Exit(1)

    llm = LLMClient(model=model)
    extractor = GraphExtractor(llm)

    console.print(f"[dim]Extracting graph from {len(traces)} traces...[/dim]")
    graph = extractor.extract(scenario, traces)

    storage.save_graph(project_id, graph)

    scenario.graph_version = graph.version
    manager.update_scenario(scenario)

    console.print(
        f"[green]Extracted graph v{graph.version}:[/green] "
        f"{len(graph.states)} states, {len(graph.transitions)} transitions"
    )


@app.command()
def optimize(project_id: str, scenario_id: str) -> None:
    """Run graph optimization on the latest extracted graph."""
    storage = _get_storage()
    manager = ScenarioManager(storage)

    try:
        scenario = manager.get_scenario(project_id, scenario_id)
    except FileNotFoundError:
        console.print("[red]Scenario not found.[/red]")
        raise typer.Exit(1)

    version = storage.latest_graph_version(project_id, scenario_id)
    if version is None:
        console.print("[red]No graph found. Run extraction first.[/red]")
        raise typer.Exit(1)

    graph = storage.load_graph(project_id, scenario_id, version)
    optimizer = GraphOptimizer()
    optimized, report = optimizer.optimize(graph)

    # Save as new version
    optimized.version = version + 1
    storage.save_graph(project_id, optimized)

    scenario.graph_version = optimized.version
    manager.update_scenario(scenario)

    console.print(f"[green]Optimized graph v{optimized.version}:[/green]")
    console.print(f"  States:      {report.original_state_count} → {report.final_state_count}")
    console.print(f"  Transitions: {report.original_transition_count} → {report.final_transition_count}")
    if report.states_removed:
        console.print(f"  Removed:     {report.states_removed}")
    if report.conflicts:
        console.print(f"  [yellow]Conflicts:   {len(report.conflicts)}[/yellow]")
        for c in report.conflicts:
            console.print(f"    - {c['state']}: {c['reason']}")


@app.command("compile")
def compile_cmd(project_id: str, scenario_id: str) -> None:
    """Compile the latest graph into a runtime artifact."""
    storage = _get_storage()
    manager = ScenarioManager(storage)

    try:
        scenario = manager.get_scenario(project_id, scenario_id)
    except FileNotFoundError:
        console.print("[red]Scenario not found.[/red]")
        raise typer.Exit(1)

    version = storage.latest_graph_version(project_id, scenario_id)
    if version is None:
        console.print("[red]No graph found. Run extraction and optimization first.[/red]")
        raise typer.Exit(1)

    graph = storage.load_graph(project_id, scenario_id, version)
    compiler = Compiler(storage)
    artifact = compiler.compile(project_id, scenario, graph)

    scenario.compiled_version = artifact.version
    manager.update_scenario(scenario)

    console.print(
        f"[green]Compiled artifact v{artifact.version}:[/green] "
        f"{len(artifact.data['graph']['states'])} states, "
        f"{len(artifact.data['graph']['transitions'])} transitions"
    )


@app.command()
def run(
    artifact_path: Path,
    max_steps: int = 100,
) -> None:
    """Start interactive runtime execution of a compiled artifact."""
    try:
        json_str = artifact_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        console.print(f"[red]File not found:[/red] {artifact_path}")
        raise typer.Exit(1)

    actions_taken = []

    def action_handler(action: str, params: dict):
        actions_taken.append(action)
        console.print(f"  [blue]Action:[/blue] {action}")
        if params:
            console.print(f"  [dim]Params: {json.dumps(params)}[/dim]")
        return {"status": "executed"}

    config = RuntimeConfig(max_steps=max_steps, action_handler=action_handler)
    engine = RuntimeEngine.from_json(json_str, config)
    state = engine.start()

    console.print(f"[bold]Runtime started at state:[/bold] {state}")
    console.print("[dim]Enter observations as JSON. Type 'quit' to exit.[/dim]\n")

    while not engine.is_terminal:
        try:
            raw = input(f"[{engine.current_state}] observation> ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Exiting.[/dim]")
            break

        if raw.strip().lower() in ("quit", "exit", "q"):
            break

        try:
            observation = json.loads(raw)
        except json.JSONDecodeError:
            console.print("[red]Invalid JSON. Try again.[/red]")
            continue

        try:
            result = engine.step(observation)
            console.print(f"  [green]→ {result.to_state}[/green]")
        except UnmatchedStateError as e:
            console.print(f"  [red]{e}[/red]")
        except RuntimeError as e:
            console.print(f"  [red]{e}[/red]")
            break

    if engine.is_terminal:
        console.print(f"\n[bold green]Terminal state reached:[/bold green] {engine.current_state}")

    console.print(f"\n[dim]Total steps: {engine.step_count}[/dim]")


if __name__ == "__main__":
    app()
