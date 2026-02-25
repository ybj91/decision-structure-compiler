# Decision Structure Compiler (DSC)

**Transform LLM-driven task execution traces into deterministic, executable decision graphs.**

The LLM is used only during compilation — never at runtime. This gives you the reasoning power of an LLM at design time with the speed, cost, and determinism of a state machine at runtime.

## How It Works

```
                  COMPILE TIME                          RUNTIME
 ┌─────────────────────────────────────┐   ┌─────────────────────────┐
 │  Scenario  ──►  LLM Simulation      │   │  Compiled    Observation │
 │  Definition      │                   │   │  Artifact ◄──── Input    │
 │                  ▼                   │   │     │                    │
 │            Execution Traces          │   │     ▼                    │
 │                  │                   │   │  Evaluate Conditions     │
 │                  ▼                   │   │     │                    │
 │         Graph Extraction (LLM)       │   │     ▼                    │
 │                  │                   │   │  Match Transition        │
 │                  ▼                   │   │     │                    │
 │         Graph Optimization           │   │     ▼                    │
 │                  │                   │   │  Dispatch Action         │
 │                  ▼                   │   │     │                    │
 │            Compilation               │   │     ▼                    │
 │                  │                   │   │  Advance State           │
 │                  ▼                   │   │                          │
 │          Compiled Artifact ──────────┼──►│  (no LLM calls)         │
 └─────────────────────────────────────┘   └─────────────────────────┘
```

**Core formal model:** `(State + Condition) → (Action, Next State)`

## Installation

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
```

## Quick Start

### 1. Create a project and scenario

```bash
dsc init "Customer Support"
dsc scenario create <project-id> "Refund Routing" --context "Route customer refund requests"
```

### 2. Add execution traces

Provide traces manually as JSON:

```bash
dsc trace add <project-id> <scenario-id> trace.json
```

Or simulate traces with an LLM:

```bash
dsc trace simulate <project-id> <scenario-id> test_input.json
```

### 3. Extract, optimize, and compile

```bash
dsc extract <project-id> <scenario-id>     # LLM extracts graph from traces
dsc optimize <project-id> <scenario-id>    # Merge states, prune, detect conflicts
dsc compile <project-id> <scenario-id>     # Produce versioned runtime artifact
```

### 4. Run deterministically

```bash
dsc run .dsc_data/projects/<id>/scenarios/<id>/compiled/v1.json
```

Or use the Python API:

```python
from dsc.compiler.compiler import CompiledArtifact
from dsc.runtime.engine import RuntimeEngine

artifact = CompiledArtifact.from_json(open("compiled/v1.json").read())
engine = RuntimeEngine.from_artifact(artifact)
engine.start()

result = engine.step({"intent": "refund", "order_age_days": 5})
print(result.action)      # "process_refund"
print(result.to_state)    # "refund_check"
```

## Architecture

```
src/dsc/
├── models/             # Pydantic data models
│   ├── conditions.py   # Condition expression AST (FieldCondition, ConditionGroup, AlwaysTrue)
│   ├── project.py      # Project model
│   ├── scenario.py     # Scenario + lifecycle stages
│   ├── trace.py        # ExecutionTrace, TraceStep
│   └── graph.py        # DecisionGraph, Transition, StateDefinition
├── storage/            # JSON filesystem persistence
├── scenario_manager/   # CRUD + lifecycle enforcement
├── trace_collector/    # Trace validation, storage, LLM simulation
├── graph_extractor/    # Three-phase LLM extraction pipeline
├── graph_optimizer/    # State merging, pruning, conflict detection
├── compiler/           # Graph → versioned JSON artifact
├── runtime/            # Deterministic execution engine
│   ├── evaluator.py    # Condition evaluation (the hot path)
│   └── engine.py       # Step-by-step state machine execution
├── llm/                # Anthropic Claude client + prompt templates
└── cli/                # Typer CLI
```

### Condition Expression AST

Conditions are structured JSON expressions that LLMs generate and the runtime evaluates deterministically:

```python
# Leaf: compare a field in the observation
FieldCondition(field="user.intent", operator=Operator.EQ, value="refund")

# Compound: combine with AND/OR/NOT
ConditionGroup(logic=LogicOperator.AND, conditions=[
    FieldCondition(field="intent", operator=Operator.EQ, value="refund"),
    FieldCondition(field="order_age_days", operator=Operator.LTE, value=30),
])

# Wildcard: default/fallback transition
AlwaysTrue()
```

Supports 10 operators: `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `in`, `not_in`, `contains`, `matches`.

### Graph Extraction Pipeline

Extraction from traces to graph uses three LLM phases:

1. **Raw Extraction** — For each trace, extract `(from_state, condition_description, action, to_state)` tuples
2. **State Normalization** — Deduplicate states across traces (e.g., "user_angry" + "customer_upset" → "customer_dissatisfied")
3. **Condition Formalization** — Convert natural language conditions into the structured AST

### Scenario Lifecycle

Scenarios progress through enforced stages with preconditions:

```
Draft → Exploration → Graph Extraction → Graph Optimization → Compiled → Production
                ↑                                                           │
                └───────────────────────────────────────────────────────────┘
                                    (recompilation)
```

## Testing

```bash
pytest              # run all 125 tests
pytest -v           # verbose output
pytest tests/test_evaluator.py   # run specific test file
```

## Design Principles

| Principle | Over |
|---|---|
| Explicit State | Implicit Reasoning |
| Determinism | Probabilistic Execution |
| Structure Extraction | Model Distillation |
| Compilation | Repeated Inference |
| Scenario Isolation | Global Agent |

This is **not** an agent framework, LLM wrapper, or prompt engineering tool. It compiles reasoning into structure.

## License

MIT
