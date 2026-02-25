# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Decision Structure Compiler** — transforms LLM-driven execution traces into deterministic, executable decision graphs (state machines / decision networks). The LLM is used only during compilation, never at runtime.

Two-phase architecture:
1. **Exploration & Compilation**: LLM simulates task execution, generates traces, extracts state transitions, produces a Decision Graph
2. **Runtime Execution**: compiled graph executes deterministically with no LLM calls (optional fallback for low-confidence paths)

Core formal model: `(State + Condition) → (Action, Next State)`

## Repository Status

This is a greenfield project in the planning stage. ARCHITECTURE.md contains the full system design. No source code, build system, or tests exist yet.

## Architecture (from ARCHITECTURE.md)

Six planned modules:
1. **Scenario Manager** — scenario creation, metadata, lifecycle (`Draft → Exploration → Graph Extraction → Graph Optimization → Compiled → Production`)
2. **Trace Collector** — storage for simulated, user-provided, and annotated execution traces
3. **Graph Extractor** — LLM-based state transition extraction and condition formalization
4. **Graph Optimizer** — state merging, unreachable node removal, graph minimization
5. **Compiler** — converts graph to executable runtime format (JSON or DSL), versioned artifacts
6. **Runtime Engine** — deterministic state execution, condition evaluation, action dispatch, optional LLM fallback

Key abstractions: **Project** (domain container) → **Scenario** (self-contained decision domain with state/observation/action schemas) → **Execution Trace** → **Decision Graph**

## Design Principles

- Explicit State over Implicit Reasoning
- Determinism over Probabilistic Execution
- Structure Extraction over Model Distillation
- Compilation over Repeated Inference
- Scenario Isolation over Global Agent

This is NOT an agent framework, LLM wrapper, or prompt engineering tool. It compiles reasoning into structure.
