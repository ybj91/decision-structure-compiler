# Decision Structure Compiler

> **Transform LLM-driven task execution traces into explicit, deterministic, executable decision graphs** — state machines or decision networks that can be compiled and executed *without* requiring an LLM at runtime.

The LLM is used **only during compilation**, never during runtime execution.

---

## Problem Statement

Large Language Models are powerful at reasoning and task decomposition, but they carry significant drawbacks:

- **Stateless** — no persistent memory across calls
- **Context-hungry** — require repeated full-context injection
- **Expensive** — high token consumption per invocation
- **Non-deterministic** — outputs vary between runs
- **Hard to audit** — difficult to version and trace decisions

However, in many **structured task domains**:

- The state space is **finite**
- The action space is **limited**
- The transition logic **stabilizes** after sufficient exploration

In such domains, repeatedly invoking an LLM is computationally inefficient. This system aims to **use LLMs to discover decision structure**, then **compile that structure into deterministic runtime graphs**.

---

## Core Concept

Execution is separated into two distinct phases:

### Phase 1: Exploration & Compilation

1. A **Scenario** is created with user-provided inputs:
   - Context, Tools, Constraints
   - Sample workflows & test cases

2. The system uses an **LLM** to:
   - Simulate task execution
   - Generate execution traces
   - Extract implicit state transitions
   - Formalize conditions & normalize states

3. The result is a structured **Decision Graph**.

### Phase 2: Runtime Execution

- The compiled Decision Graph is loaded
- **No LLM calls required** at runtime
- Execution is **deterministic**, **state-driven**, **low-latency**, and **low-cost**
- Optional LLM fallback when runtime confidence is low *(configurable)*

---

## Key Abstractions

### Project

A **Project** represents a domain or system. It may contain multiple Scenarios.

### Scenario

A **Scenario** is a self-contained decision domain. It includes:

| Component              | Description                        |
|------------------------|------------------------------------|
| Context definition     | Domain knowledge and constraints   |
| State schema           | Possible states the system can occupy |
| Observation schema     | Inputs that drive transitions      |
| Action definitions     | Available actions at each state    |
| Tool definitions       | External tools the system can invoke |
| Execution traces       | Sample or simulated trace data     |
| Decision graph         | The compiled output                |

**Lifecycle stages:**

```
Draft → Exploration → Graph Extraction → Graph Optimization → Compiled → Production
```

### Execution Trace

An execution trace captures a full decision path:

- Initial state
- Observations & decisions
- Actions & next states
- Tool outcomes

Traces may be **user-provided**, **LLM-simulated**, or **hybrid**.

### Decision Graph

A Decision Graph formalizes the transition logic:

- Finite state set
- Condition definitions
- Transition rules
- Action bindings

> **Formally:** `(State + Condition) → (Action, Next State)`

---

## What This System Is NOT

| | |
|---|---|
| :x: | A prompt engineering playground |
| :x: | An agent framework |
| :x: | An LLM wrapper |
| :x: | An LLM-powered runtime executor |
| :x: | An attempt to build a smaller LLM |

> **This system compiles reasoning into structure.**

---

## Design Principles

| Principle | Over |
|---|---|
| Explicit State | Implicit Reasoning |
| Determinism | Probabilistic Execution |
| Structure Extraction | Model Distillation |
| Compilation | Repeated Inference |
| Scenario Isolation | Global Agent |

---

## Expected Modules

### 1. Scenario Manager
- Scenario creation, metadata, and lifecycle management

### 2. Trace Collector
- Storage for simulated, user-provided, and annotated traces

### 3. Graph Extractor
- Uses LLM to extract state transitions, normalize labels, and formalize conditions

### 4. Graph Optimizer
- Merges equivalent states, removes unreachable nodes, minimizes the graph

### 5. Compiler
- Converts graph to executable runtime format (JSON or DSL), produces versioned artifacts

### 6. Runtime Engine
- Deterministic state execution, condition evaluation, action dispatch, optional LLM fallback

---

## LLM Usage Policy

LLMs are used **only** for:

- Trace simulation
- Structure extraction
- State normalization
- Condition formalization

> LLMs are **never required** for production execution.

---

## Success Criteria

A Scenario is considered successful when:

- [x] **≥ 80%** of test cases execute without LLM fallback
- [x] The state graph **stabilizes**
- [x] The number of states **converges**
- [x] Transitions become **deterministic**
- [x] Execution cost **drops significantly** vs. LLM-driven execution

---

## Long-Term Vision

This system explores a new architecture paradigm — shifting intelligence to **compile-time** rather than runtime.

| LLM Role | Not |
|---|---|
| Structure Discoverer | Always-on executor |
| Policy Generator | |
| Control Flow Synthesizer | |