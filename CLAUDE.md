# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Decision Structure Compiler (DSC)** -- transforms LLM-driven execution traces into deterministic, executable decision graphs. The LLM is used only during compilation, never at runtime.

Two-phase architecture:
1. **Compile time**: LLM simulates traces, extracts state transitions, normalizes states, formalizes conditions into structured AST
2. **Runtime**: compiled graph executes deterministically with zero LLM calls

Core formal model: `(State + Condition) -> (Action, Next State)`

## Build & Test

```bash
pip install -e ".[dev]"   # install with dev dependencies
pytest                     # run all 125 tests
dsc --help                 # CLI entrypoint
```

## Project Structure

```
src/dsc/
  models/               # Pydantic data models
    conditions.py       # Condition AST: FieldCondition, ConditionGroup, AlwaysTrue
    project.py          # Project model
    scenario.py         # Scenario + ScenarioStatus lifecycle enum + VALID_TRANSITIONS
    trace.py            # ExecutionTrace, TraceStep, TraceSource
    graph.py            # DecisionGraph, Transition, StateDefinition
  storage/
    filesystem.py       # JSON file persistence (all CRUD for projects/scenarios/traces/graphs/compiled)
  scenario_manager/
    manager.py          # ScenarioManager: CRUD + lifecycle transition validation
  trace_collector/
    collector.py        # TraceCollector: validation (chain consistency) + storage
    simulator.py        # TraceSimulator: LLM-based trace generation
  graph_extractor/
    extractor.py        # GraphExtractor: 3-phase pipeline (extract -> normalize -> formalize)
  graph_optimizer/
    optimizer.py        # GraphOptimizer: unreachable pruning, dedup, equivalent state merge, conflict detection
  compiler/
    compiler.py         # Compiler: graph -> versioned self-contained JSON artifact (CompiledArtifact)
  runtime/
    evaluator.py        # evaluate(): pure condition evaluation (hot path, no side effects)
    engine.py           # RuntimeEngine: step-by-step execution, priority-based transition matching
  llm/
    client.py           # LLMClient: Anthropic SDK wrapper with structured_request() via tool_use
    prompts.py          # All prompt templates + JSON schemas for LLM interactions
  cli/
    main.py             # Typer CLI: init, scenario, trace, extract, optimize, compile, run

tests/
  conftest.py           # Shared fixtures (tmp_data_dir, storage)
  test_models.py        # Model serialization roundtrip + storage CRUD
  test_evaluator.py     # Condition evaluator: all operators, nesting, edge cases
  test_scenario_manager.py  # CRUD + full lifecycle transitions
  test_trace_collector.py   # Trace validation + storage
  test_graph_extractor.py   # Extraction with mocked LLM responses
  test_graph_optimizer.py   # Pruning, merging, conflict detection
  test_compiler.py      # Artifact generation + versioning
  test_runtime.py       # Engine execution with pre-built artifacts

examples/
  full_pipeline/        # Complete workflow: scenario -> LLM simulation -> extraction -> runtime
  customer_support/     # Pre-built artifact + 4 hand-written traces
  content_moderation/   # Multi-stage filtering pipeline
  programmatic_api/     # Build everything from Python code, no CLI/LLM
```

## Key Architecture Decisions

### Condition Expression AST (`models/conditions.py`)
Discriminated union via Pydantic `type` field:
- `FieldCondition`: leaf comparison with dot-path field access, 10 operators (eq/ne/gt/lt/gte/lte/in/not_in/contains/matches)
- `ConditionGroup`: AND/OR/NOT compound, nests arbitrarily
- `AlwaysTrue`: wildcard/default fallback

### Graph Extraction (`graph_extractor/extractor.py`)
Three-phase LLM pipeline:
- **Phase A**: per-trace raw transition extraction (tool: `extract_transitions`)
- **Phase B**: cross-trace state normalization/dedup (tool: `normalize_states`)
- **Phase C**: condition formalization into AST (tool: `formalize_conditions`)

### Runtime Evaluation (`runtime/evaluator.py`)
Pure function `evaluate(condition, observation) -> bool`. Handles nested field paths via `resolve_field()`, type mismatches return False, missing fields return False.

### Scenario Lifecycle (`models/scenario.py`)
`Draft -> Exploration -> Graph Extraction -> Graph Optimization -> Compiled -> Production` with loop back from Production to Exploration. Preconditions enforced in `ScenarioManager.transition()`.

### Storage Layout
```
{data_dir}/projects/{project_id}/
  project.json
  scenarios/{scenario_id}/
    scenario.json
    traces/{trace_id}.json
    graphs/v{version}.json
    compiled/v{version}.json
```

### LLM Client (`llm/client.py`)
Uses Anthropic `tool_use` with `tool_choice={"type": "tool", "name": ...}` to force structured JSON output. All prompt templates in `llm/prompts.py`.

## Design Principles

- Explicit State over Implicit Reasoning
- Determinism over Probabilistic Execution
- Structure Extraction over Model Distillation
- Compilation over Repeated Inference
- Scenario Isolation over Global Agent

This is NOT an agent framework, LLM wrapper, or prompt engineering tool. It compiles reasoning into structure.
