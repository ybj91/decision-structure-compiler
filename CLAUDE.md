# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Decision Structure Compiler** — transforms LLM-driven execution traces into deterministic, executable decision graphs (state machines / decision networks). The LLM is used only during compilation, never at runtime.

Two-phase architecture:
1. **Exploration & Compilation**: LLM simulates task execution, generates traces, extracts state transitions, produces a Decision Graph
2. **Runtime Execution**: compiled graph executes deterministically with no LLM calls (optional fallback for low-confidence paths)

Core formal model: `(State + Condition) → (Action, Next State)`

## Repository Status

Fully implemented Python project. Install with `pip install -e ".[dev]"`. Run tests with `pytest`.

## Build & Test

```bash
pip install -e ".[dev]"   # install with dev dependencies
pytest                     # run all 125 tests
dsc --help                 # CLI entrypoint
```

## Architecture

Package: `src/dsc/` — nine modules:

1. **models/** — Pydantic data models (conditions AST, project, scenario, trace, graph)
2. **storage/** — JSON filesystem persistence
3. **scenario_manager/** — CRUD + lifecycle transitions (`Draft → Exploration → Graph Extraction → Graph Optimization → Compiled → Production`)
4. **trace_collector/** — trace storage/validation + LLM simulation
5. **graph_extractor/** — three-phase LLM extraction pipeline (raw extraction → state normalization → condition formalization)
6. **graph_optimizer/** — networkx-based state merging, pruning, conflict detection
7. **compiler/** — graph → versioned self-contained JSON artifact
8. **runtime/** — deterministic condition evaluator + execution engine
9. **llm/** — Anthropic Claude client wrapper + prompt templates
10. **cli/** — Typer CLI

Key abstractions: **Project** → **Scenario** → **ExecutionTrace** → **DecisionGraph** → **CompiledArtifact**

### Condition Expression AST

The core type system for deterministic evaluation: `FieldCondition` (leaf comparisons with dot-path field access), `ConditionGroup` (AND/OR/NOT compound), `AlwaysTrue` (wildcard). Discriminated union via Pydantic `type` field.

## Design Principles

- Explicit State over Implicit Reasoning
- Determinism over Probabilistic Execution
- Structure Extraction over Model Distillation
- Compilation over Repeated Inference
- Scenario Isolation over Global Agent

This is NOT an agent framework, LLM wrapper, or prompt engineering tool. It compiles reasoning into structure.
