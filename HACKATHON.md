# Decision Structure Compiler — Compile AI Reasoning Into Deterministic Logic

> *Use the LLM once at design time. Run deterministic decisions forever — zero API calls, zero latency, zero hallucinations.*

**Keywords:** `AI Compiler` `Deterministic AI` `Decision Graphs` `LLM Distillation` `Zero-Inference Runtime` `Structured Decision Making` `AI Governance` `Condition AST` `Graph Optimization` `Compile-Time AI`

---

## Description

### The Problem

Today's AI-powered workflows have a fundamental flaw: they call an LLM on every single execution. Every customer support ticket, every content moderation decision, every approval routing — each one burns tokens, adds latency, and introduces unpredictability. Teams build "AI agents" that are really just expensive, non-deterministic if-else statements running on someone else's GPU.

This creates real operational pain:

- **Cost scales linearly** — every decision costs tokens, forever
- **Reliability is a gamble** — the same input can produce different outputs across runs
- **Latency is unavoidable** — every decision waits on a network round-trip
- **Auditability is near-impossible** — you can't inspect or version-control a probability distribution
- **Outages become your outages** — when the LLM provider goes down, your system goes down

### Our Solution

**Decision Structure Compiler (DSC)** introduces a two-phase architecture that separates *thinking* from *doing*:

**Phase 1 — Compile Time (LLM-powered):**

- Define scenarios and simulate execution traces using an LLM
- Extract state transitions across all traces
- Normalize and deduplicate the decision space
- Formalize conditions into a structured AST (Abstract Syntax Tree) with 10 comparison operators, arbitrary nesting, and dot-path field access
- Optimize the graph: prune unreachable states, merge equivalent states, detect conflicts
- Output a **versioned, self-contained compiled artifact**

**Phase 2 — Runtime (Zero LLM):**

- Load the compiled artifact (pure JSON)
- Evaluate conditions deterministically against live observations
- Execute state transitions with priority-based matching
- **No API calls. No tokens. No network. No surprises.**

### How It Works — The Core Pipeline

```
Scenario -> Traces -> Raw Transitions -> Normalized States -> Formalized Conditions -> Optimized Graph -> Compiled Artifact -> Deterministic Runtime
```

Each stage is independently testable and inspectable. The formal model at the heart of DSC is:

```
(Current State + Condition) -> (Action, Next State)
```

Conditions are not strings or prompts — they are structured AST nodes (`FieldCondition`, `ConditionGroup`, `AlwaysTrue`) that evaluate to boolean with zero ambiguity.

### What Makes This Different

| Traditional AI Workflow | DSC Approach |
|---|---|
| LLM called on every request | LLM used once at compile time |
| Non-deterministic outputs | Deterministic execution, every time |
| Cost scales with usage | Fixed cost at compile time, free at runtime |
| Black-box decisions | Inspectable, versionable decision graphs |
| Depends on API availability | Runs offline, self-contained |
| Hard to test | 125+ unit tests, every layer independently testable |

### Built With

- **Python** with **Pydantic** models for type-safe data structures
- **Anthropic Claude API** with structured `tool_use` for compile-time extraction
- **Typer CLI** for full command-line workflow
- **Three-phase LLM extraction pipeline** (extract -> normalize -> formalize)
- **Graph optimizer** with unreachable pruning, deduplication, equivalent state merging, and conflict detection
- **Pure-function runtime evaluator** — the hot path has zero side effects

---

## How This Project Addresses the Executive Challenge: "Changing How We Work in the Era of AI"

DSC fundamentally redefines how organizations integrate AI into their workflows — shifting from perpetual AI dependency to AI-compiled autonomy.

### From "AI as a Service" to "AI as a Compiler"

Today, most teams treat LLMs as a runtime dependency — every decision, every ticket, every approval calls an API. This is expensive, fragile, and impossible to audit. DSC flips this model: the LLM is used *once* at design time to think through the decision space, extract structured logic, and compile it into a deterministic artifact. After that, the AI's job is done. The compiled logic runs forever — no API calls, no tokens, no latency, no hallucinations.

### This changes how we work in three concrete ways:

**1. Decisions become governable.**
Instead of trusting a black-box model on every execution, teams get inspectable decision graphs they can review, version-control, and approve through existing change management processes. AI generates the logic; humans govern it — a workflow that actually fits regulated industries and enterprise standards.

**2. Teams shift from prompt engineering to decision engineering.**
Rather than endlessly tuning prompts and hoping for consistent outputs, teams design scenarios, define states, and formalize conditions. This is a durable, transferable engineering discipline — not a workaround for model unpredictability. The result is testable with standard software practices (we have 125+ unit tests proving it).

**3. AI value is captured permanently, not rented.**
When an LLM provider has an outage, DSC-compiled systems keep running. When pricing changes, operating costs don't move. When models get deprecated, compiled artifacts still work. Organizations extract intelligence from AI once and own it forever — scaling becomes virtually free because every additional runtime execution costs zero tokens.

### The Bottom Line

Most AI adoption adds ongoing cost and dependency. DSC is the opposite — it uses AI to build things that no longer need AI. That's not incremental improvement; it's a fundamentally different way of working in the era of AI.
