# Decision Structure Compiler (DSC)

**Transform LLM-driven task execution traces into deterministic, executable decision graphs.**

The LLM is used only during compilation -- never at runtime. This gives you the reasoning power of an LLM at design time with the speed, cost, and determinism of a state machine at runtime.

## Why DSC?

LLMs are powerful reasoners, but using them at runtime is expensive, slow, non-deterministic, and hard to audit. Yet in many domains -- customer support, content moderation, order processing, approval workflows -- the decision logic is **finite and stable**. The same types of inputs lead to the same types of decisions.

DSC captures this insight: **use the LLM to discover the decision structure once, then compile it into a state machine that runs forever without the LLM.**

| | LLM at Runtime | DSC (compiled) |
|---|---|---|
| **Cost per decision** | ~$0.01-0.10 (API call) | ~$0 (local evaluation) |
| **Latency** | 500ms-5s | <1ms |
| **Determinism** | No (varies between runs) | Yes (same input = same output) |
| **Auditability** | Hard (opaque reasoning) | Full (every transition is explicit) |
| **Offline capable** | No (needs API) | Yes |

## How It Works

```
                  COMPILE TIME                          RUNTIME
 +-------------------------------------+   +-------------------------+
 |  Scenario  -->  LLM Simulation      |   |  Compiled    Observation |
 |  Definition      |                   |   |  Artifact <---- Input    |
 |                  v                   |   |     |                    |
 |            Execution Traces          |   |     v                    |
 |                  |                   |   |  Evaluate Conditions     |
 |                  v                   |   |     |                    |
 |         Graph Extraction (LLM)       |   |     v                    |
 |                  |                   |   |  Match Transition        |
 |                  v                   |   |     |                    |
 |         Graph Optimization           |   |     v                    |
 |                  |                   |   |  Dispatch Action         |
 |                  v                   |   |     |                    |
 |            Compilation               |   |     v                    |
 |                  |                   |   |  Advance State           |
 |                  v                   |   |                          |
 |          Compiled Artifact ----------+-->|  (no LLM calls)         |
 +-------------------------------------+   +-------------------------+
```

The formal model: **`(State + Condition) -> (Action, Next State)`**

At each step, the runtime looks at the current state, evaluates the observation against the transition conditions (in priority order), takes the first match, dispatches the action, and moves to the next state.

## Installation

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
```

## Key Concepts

### Project

A **Project** is a top-level container for a domain. Think of it as a workspace. A project can contain multiple scenarios.

```bash
dsc init "E-Commerce Platform"
```

### Scenario

A **Scenario** is a self-contained decision domain. It defines everything the system needs to know:

| Component | What it is | Example |
|---|---|---|
| **Context** | Natural language description of the domain | "Handle customer support requests for an online store" |
| **Observation Schema** | The fields the system receives at runtime | `intent` (string), `order_age_days` (number), `customer_tier` (string) |
| **Actions** | What the system can do | `approve_refund`, `escalate_to_human`, `send_confirmation` |
| **Tools** | External systems actions can invoke | `payment_processor`, `ticket_system`, `email_service` |
| **Constraints** | Rules the LLM must follow during trace simulation | "Auto-refunds only for amounts under $100" |

The observation schema is critical -- it defines the vocabulary of your decision logic. Conditions in the compiled graph reference these fields. At runtime, each step receives an observation dict with these fields, and transitions are evaluated against them.

**Creating a scenario via CLI:**

```bash
dsc scenario create <project-id> "Refund Routing" --context "Route customer refund requests"
```

**Creating a scenario programmatically (with full schema):**

```python
from dsc.models.scenario import Scenario, ObservationSchema, ObservationField, ActionDefinition

scenario = Scenario(
    id="refund-routing",
    project_id="my-project",
    name="Refund Routing",
    context="Handle customer refund requests. Approve small refunds automatically, escalate large ones.",
    observation_schema=ObservationSchema(fields={
        "intent": ObservationField(type="string", description="Customer intent"),
        "order_age_days": ObservationField(type="number", description="Days since order"),
        "refund_amount": ObservationField(type="number", description="Requested refund amount"),
        "customer_tier": ObservationField(type="string", description="standard or premium"),
    }),
    actions={
        "approve_refund": ActionDefinition(name="approve_refund", description="Approve the refund", tool="payment_api"),
        "deny_refund": ActionDefinition(name="deny_refund", description="Deny with explanation"),
        "escalate": ActionDefinition(name="escalate", description="Send to human agent", tool="ticket_system"),
    },
    constraints=[
        "Auto-approve refunds only if amount is under $100 and order is less than 30 days old",
        "Premium customers get extended return windows (90 days)",
        "Always escalate if unsure",
    ],
)
```

### Execution Trace

An **Execution Trace** is a recorded path through a scenario -- a sequence of states, observations, decisions, and actions. Traces are the raw material from which decision graphs are extracted.

There are three ways to get traces:

**1. LLM simulation (recommended).** Give the system test inputs and let the LLM reason through them:

```bash
# test_input.json: {"intent": "refund", "order_age_days": 5, "refund_amount": 45.00}
dsc trace simulate <project-id> <scenario-id> test_input.json
```

The LLM receives your scenario definition (context, actions, tools, constraints) and the test input, then simulates a realistic execution step by step, recording its reasoning at every decision point.

**2. User-provided traces.** Write traces by hand from domain expertise:

```bash
dsc trace add <project-id> <scenario-id> my_trace.json
```

**3. Hybrid.** Mix LLM-simulated and hand-written traces. Hand-written traces are useful for encoding edge cases or specific business rules the LLM might miss.

A trace looks like this:

```json
{
  "id": "trace-refund-happy",
  "scenario_id": "refund-routing",
  "source": "user",
  "initial_state": "triage",
  "steps": [
    {
      "state": "triage",
      "observation": {"intent": "refund", "order_age_days": 5, "refund_amount": 45.00},
      "decision": "Customer wants a refund. Order is recent and amount is small. Approve.",
      "action": "approve_refund",
      "action_params": {"amount": 45.00},
      "tool_result": {"refund_id": "ref-001", "status": "processed"},
      "next_state": "resolved"
    }
  ]
}
```

The `decision` field is important -- it captures **why** the LLM chose this action. During graph extraction, the LLM uses these decision descriptions to formalize the conditions. More traces covering more paths produce a more complete graph.

### Decision Graph

A **Decision Graph** is the extracted, structured representation of the decision logic. It contains:

- **States** -- named nodes (e.g., `triage`, `billing_review`, `resolved`)
- **Transitions** -- directed edges between states, each with a condition, action, and priority
- **Initial state** -- where execution begins
- **Terminal states** -- where execution ends

Each transition has a **condition expression** that determines when it fires. Conditions are structured, not natural language -- they're evaluated deterministically at runtime.

### Condition Expressions

The condition AST is the core type system that bridges LLM reasoning and deterministic execution. Three types:

**FieldCondition** -- compare a field in the observation against a value:

```python
FieldCondition(field="refund_amount", operator=Operator.LTE, value=100)
# Evaluates: observation["refund_amount"] <= 100
```

Fields support dot-path notation for nested access: `user.profile.tier` accesses `observation["user"]["profile"]["tier"]`.

10 operators: `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `in`, `not_in`, `contains`, `matches` (regex).

**ConditionGroup** -- combine conditions with AND/OR/NOT:

```python
ConditionGroup(logic=LogicOperator.AND, conditions=[
    FieldCondition(field="duplicate_confirmed", operator=Operator.EQ, value=True),
    FieldCondition(field="refund_amount", operator=Operator.LTE, value=100),
])
# Evaluates: duplicate_confirmed == True AND refund_amount <= 100
```

Groups nest arbitrarily: `(A AND (B OR C)) AND NOT D`.

**AlwaysTrue** -- wildcard/default transition. Fires when nothing else matches:

```python
AlwaysTrue()
# Always evaluates to True -- used for fallback transitions
```

In a compiled graph, transitions from a state are evaluated in priority order (lower number = higher priority). The first matching transition wins. `AlwaysTrue` transitions typically have high priority numbers (e.g., 100) so they only fire as a last resort.

### Compiled Artifact

A **Compiled Artifact** is a self-contained JSON file that includes everything the runtime needs:

- The full decision graph (states, transitions with serialized conditions)
- Action and tool definitions from the scenario
- Compilation metadata (version, source traces, stats)

Artifacts are versioned (v1, v2, ...). Each compilation produces a new version. You can run any version at any time.

```bash
dsc compile <project-id> <scenario-id>
# Produces: .dsc_data/projects/<id>/scenarios/<id>/compiled/v1.json
```

### Scenario Lifecycle

Scenarios progress through enforced stages with preconditions at each transition:

```
Draft -> Exploration -> Graph Extraction -> Graph Optimization -> Compiled -> Production
            ^                                                                    |
            +--------------------------------------------------------------------+
                                      (recompilation)
```

| Stage | What happens | Precondition |
|---|---|---|
| **Draft** | Define scenario, schemas, actions, tools | -- |
| **Exploration** | Simulate or add traces | -- |
| **Graph Extraction** | LLM extracts graph from traces | At least 1 trace |
| **Graph Optimization** | Merge states, prune, detect conflicts | Graph extracted |
| **Compiled** | Produce versioned runtime artifact | Graph optimized |
| **Production** | Artifact deployed for runtime execution | Artifact compiled |

From Production, you can loop back to Exploration to add more traces and recompile -- this is how you iteratively improve the graph.

## Usage

### CLI Workflow

```bash
# 1. Create a project
dsc init "My Project"

# 2. Create a scenario
dsc scenario create <project-id> "Support Bot" --context "Handle customer support"

# 3. Simulate traces with LLM (or add manual traces)
dsc trace simulate <project-id> <scenario-id> test_case_1.json
dsc trace simulate <project-id> <scenario-id> test_case_2.json
dsc trace simulate <project-id> <scenario-id> test_case_3.json

# 4. Extract graph from traces
dsc extract <project-id> <scenario-id>

# 5. Optimize the graph
dsc optimize <project-id> <scenario-id>

# 6. Compile to artifact
dsc compile <project-id> <scenario-id>

# 7. Run interactively
dsc run .dsc_data/projects/<id>/scenarios/<id>/compiled/v1.json
```

The interactive runtime prompts you to enter observation JSON at each step:

```
Runtime started at state: triage
Enter observations as JSON. Type 'quit' to exit.

[triage] observation> {"issue_type": "billing", "severity": "medium"}
  Action: lookup_billing_history
  -> billing_review

[billing_review] observation> {"duplicate_confirmed": true, "refund_amount": 29.99}
  Action: process_refund
  -> refund_issued

[refund_issued] observation> {"customer_satisfied": true}
  Action: close_ticket
  -> resolved

Terminal state reached: resolved
```

### Python API

```python
from dsc.compiler.compiler import CompiledArtifact
from dsc.runtime.engine import RuntimeEngine, RuntimeConfig

# Load a compiled artifact
artifact = CompiledArtifact.from_json(open("compiled/v1.json").read())

# Set up an action handler (optional -- called when actions fire)
def on_action(action_name: str, params: dict):
    print(f"Executing: {action_name} with {params}")
    return {"status": "ok"}  # result available in step.action_result

config = RuntimeConfig(action_handler=on_action)

# Create and start the engine
engine = RuntimeEngine.from_artifact(artifact, config)
engine.start()  # returns initial state name

# Feed observations step by step
result = engine.step({"intent": "refund", "order_age_days": 5})
print(result.action)       # "approve_refund"
print(result.to_state)     # "refund_approved"

# Or run multiple observations at once (stops at terminal state)
results = engine.run([
    {"intent": "refund", "order_age_days": 5},
    {"refund_confirmed": True},
])

# Check state
engine.current_state   # "resolved"
engine.is_terminal     # True
engine.step_count      # 2
engine.history         # list of StepResult objects
```

### Graph Extraction Pipeline

The extraction pipeline is the core intelligence of DSC. It turns raw traces into a structured graph in three LLM phases:

**Phase A -- Raw Extraction.** For each trace independently, the LLM extracts transition tuples:

```
Input:  trace with steps [triage -> billing_review -> refund_issued -> resolved]
Output: [
  (triage, "customer reports billing issue", lookup_billing, billing_review),
  (billing_review, "duplicate confirmed, amount under $100", process_refund, refund_issued),
  (refund_issued, "customer satisfied", close_ticket, resolved),
]
```

**Phase B -- State Normalization.** The LLM sees all states from all traces and deduplicates:

```
Input:  ["triage", "initial_assessment", "intake", "billing_review", ...]
Output: {"initial_assessment" -> "triage", "intake" -> "triage", ...}
```

This is critical when different traces use different names for the same concept.

**Phase C -- Condition Formalization.** The LLM converts natural language conditions into the structured condition AST:

```
Input:  "duplicate confirmed, amount under $100"
Output: {"type": "group", "logic": "and", "conditions": [
           {"type": "field", "field": "duplicate_confirmed", "operator": "eq", "value": true},
           {"type": "field", "field": "refund_amount", "operator": "lte", "value": 100}
         ]}
```

The more traces you provide, the more complete the graph. Each trace is a sample path; the LLM generalizes from the samples to produce conditions that cover the full space.

### Graph Optimization

After extraction, the optimizer cleans up the graph:

- **Unreachable state removal** -- BFS from initial state, prune anything disconnected
- **Duplicate transition merging** -- same from/to/action/condition get merged (source traces combined)
- **Equivalent state merging** -- states with identical outgoing transitions collapse into one
- **Conflict detection** -- flags transitions from the same state with identical conditions but different outcomes

The optimizer produces a report with statistics and any conflicts that need manual resolution.

### Unmatched Observations

What happens when the runtime encounters an observation that matches no transition from the current state?

1. **Default transition** -- if the state has an `AlwaysTrue` transition, it fires as fallback
2. **UnmatchedStateError** -- if no default exists, the engine raises an error

This is by design: the system fails loudly rather than guessing. To handle more cases, add more traces and recompile.

## Architecture

```
src/dsc/
  models/             # Pydantic data models
    conditions.py     # Condition expression AST (FieldCondition, ConditionGroup, AlwaysTrue)
    project.py        # Project model
    scenario.py       # Scenario + lifecycle stages
    trace.py          # ExecutionTrace, TraceStep
    graph.py          # DecisionGraph, Transition, StateDefinition
  storage/            # JSON filesystem persistence
  scenario_manager/   # CRUD + lifecycle enforcement
  trace_collector/    # Trace validation, storage, LLM simulation
  graph_extractor/    # Three-phase LLM extraction pipeline
  graph_optimizer/    # State merging, pruning, conflict detection (networkx)
  compiler/           # Graph -> versioned JSON artifact
  runtime/            # Deterministic execution engine
    evaluator.py      # Condition evaluation (the hot path -- pure, no side effects)
    engine.py         # Step-by-step state machine execution
  llm/                # Anthropic Claude client + prompt templates
  cli/                # Typer CLI
```

## Examples

Four runnable examples in [`examples/`](examples/). No LLM API key needed.

### Full Pipeline (start here)

**This is the most important example.** It shows the complete DSC workflow: define a scenario, let the LLM simulate traces, extract a decision graph, optimize, compile, and run deterministically. No hand-written traces.

```bash
python examples/full_pipeline/demo.py
```

The scenario is a **tech support triage system** that handles password resets, billing disputes, and service outages.

**What happens step by step:**

**Step 1 -- Define the scenario.** You describe the domain, available actions (password reset, refund, escalate...), tools (auth service, billing API, status page), and constraints ("auto-refunds only under $100").

**Step 2 -- LLM simulates traces.** Given 3 test inputs, the LLM reasons through each one and produces a full execution trace. This is where the LLM's intelligence gets captured:

```
  Trace 1: account (low) -> 2 steps
    triage -> [initiate_password_reset] -> awaiting_confirmation
      This is a standard account access issue. The customer forgot their
      password. Route to account recovery flow.
    awaiting_confirmation -> [close_ticket] -> resolved
      Customer confirmed they received the reset link. Issue resolved.

  Trace 2: billing (medium) -> 3 steps
    triage -> [lookup_billing_history] -> billing_review
      This is a billing dispute about a duplicate charge. Need to verify.
    billing_review -> [process_refund] -> refund_issued
      Duplicate charge confirmed. Amount is under $100 so auto-refund is
      authorized without manager approval.
    refund_issued -> [close_ticket] -> resolved

  Trace 3: technical (critical) -> 3 steps
    triage -> [check_system_status] -> incident_detected
      Critical severity reporting a full service outage. Must check status.
    incident_detected -> [notify_known_incident] -> monitoring
      Known active incident. Notify customer about the ETA.
    monitoring -> [close_ticket] -> resolved
```

**Step 3 -- LLM extracts the decision graph.** Three-phase pipeline:
- **Phase A:** Extract raw transitions from each trace
- **Phase B:** Normalize states across all traces (deduplicate synonyms)
- **Phase C:** Formalize natural language conditions into structured expressions

The LLM turns reasoning like *"amount is under $100 so auto-refund is authorized"* into:

```
billing_review --[(duplicate_confirmed eq True AND refund_amount lte 100)]--> process_refund
billing_review --[(duplicate_confirmed eq True AND refund_amount gt 100)]--> escalate_to_human
```

**Steps 4-5 -- Optimize and compile.** Prune unreachable states, merge duplicates, detect conflicts, produce a self-contained JSON artifact.

**Step 6 -- Run deterministically.** The compiled graph executes with zero LLM calls:

```
  BILLING REFUND -- duplicate charge under $100
    [triage] + {issue_type=billing, severity=medium}
      -> lookup_billing_history -> [billing_review]
    [billing_review] + {duplicate_confirmed=True, refund_amount=29.99}
      -> process_refund -> [refund_issued]
    [refund_issued] + {customer_satisfied=True}
      -> close_ticket -> [resolved]
    Result: RESOLVED in 3 steps

  BILLING ESCALATION -- duplicate charge over $100
    [triage] + {issue_type=billing, severity=medium}
      -> lookup_billing_history -> [billing_review]
    [billing_review] + {duplicate_confirmed=True, refund_amount=250.0}
      -> escalate_to_human -> [resolved]
    Result: RESOLVED in 2 steps
```

**The result:** 8 LLM calls at compile time produced a 7-state, 15-transition graph that handles 5 different runtime scenarios deterministically. The LLM reasoned once; the state machine runs forever.

> This demo mocks the LLM responses so you can run it without an API key. In production, replace the mock with `LLMClient()` and Claude generates everything automatically.

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

## When to Use DSC

**Good fit:**
- Customer support routing and triage
- Content moderation pipelines
- Approval workflows (loan applications, expense reports)
- Order processing and fulfillment
- Any domain where the same types of inputs lead to the same types of decisions

**Not a good fit:**
- Open-ended creative tasks (writing, brainstorming)
- Tasks where the state space is truly unbounded
- One-off tasks that won't be repeated

The litmus test: *"If I saw 50 examples of this task, would I start seeing patterns?"* If yes, DSC can compile those patterns.

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
