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

## Examples

Three runnable examples in [`examples/`](examples/). No LLM API key needed.

### Customer Support Routing

Routes customer inquiries through intent classification, refund evaluation (with VIP overrides), and escalation.

```bash
python examples/customer_support/demo.py
```

**What it demonstrates:**
- Intent-based routing (`refund`, `question`, `complaint`, unknown)
- Compound conditions: refund approved if `order_age_days <= 30 AND item_condition in [unopened, defective]`
- VIP override: premium customers get courtesy refunds even outside the return window
- Default/wildcard transitions: unknown intents fall through to general inquiry handling
- Terminal states: `resolved` (happy ending) vs `escalated` (handed to human)

**Sample output:**
```
SCENARIO 1: Customer wants a refund (eligible)

  State: greeting
  Observation: {'intent': 'refund', 'message': 'I want to return my order'}
    -> Action: acknowledge_refund_request
  -> New state: refund_evaluation

  State: refund_evaluation
  Observation: {'order_age_days': 12, 'order_amount': 89.99, 'item_condition': 'unopened'}
    -> Action: approve_refund {'refund_method': 'original_payment'}
  -> New state: refund_approved
  ...
  RESULT: Terminal (3 steps)
```

The [`traces/`](examples/customer_support/traces/) directory contains 4 hand-written execution traces showing different paths through the scenario. These are the kind of traces you'd provide (or have the LLM simulate) as input to the extraction pipeline.

### Content Moderation Pipeline

Multi-stage content filtering: toxicity check, policy check, spam check. Each stage has threshold-based routing.

```bash
python examples/content_moderation/demo.py
```

**What it demonstrates:**
- Sequential pipeline: `intake -> toxicity -> policy -> spam -> published`
- Threshold-based conditions: `toxicity_score > 0.8` rejects, `> 0.5` sends to human review
- Compound conditions: publish only if `spam_score <= 0.7 AND author_reputation >= 50`
- Content type routing: images/video skip text analysis and go directly to human review
- Multiple terminal states: `published`, `rejected`, `held_for_review`

### Programmatic API (Order Fulfillment)

Build a complete scenario, graph, optimizer, and runtime from Python code. No CLI, no LLM, no files.

```bash
python examples/programmatic_api/build_and_run.py
```

**What it demonstrates:**
- Defining a `Scenario` with observation schema and action definitions
- Manually constructing a `DecisionGraph` with states and transitions
- Running the `GraphOptimizer` (unreachable state pruning, conflict detection)
- Compiling to a versioned artifact with the `Compiler`
- Executing 4 different order scenarios through the `RuntimeEngine`
- Retry loops: payment pending stays in `payment_validation` until approved/declined

**The decision graph:**
```
  order_received
       |
       v
  payment_validation --[declined]--> cancelled
       |                                ^
    [approved]                          |
       v                                |
  inventory_check ---[no stock]---------+
       |
    [in stock]
       v
  shipping ---[express/standard]--> completed
```

### Trace Format

Traces are JSON files capturing decision paths. Here's the structure:

```json
{
  "id": "trace-refund-happy",
  "scenario_id": "customer-support",
  "source": "user",
  "initial_state": "greeting",
  "steps": [
    {
      "state": "greeting",
      "observation": {"intent": "refund", "customer_tier": "standard"},
      "decision": "Customer wants a refund. Route to evaluation.",
      "action": "acknowledge_refund_request",
      "action_params": {},
      "tool_result": null,
      "next_state": "refund_evaluation"
    }
  ],
  "metadata": {"test_case": "happy_path"}
}
```

Each step captures: **what state we're in**, **what we observe**, **why we decided** (for LLM extraction), **what action we take**, and **where we go next**. The chain must be consistent: each step's `next_state` must match the following step's `state`.

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
