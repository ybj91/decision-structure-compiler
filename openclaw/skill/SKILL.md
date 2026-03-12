---
name: dsc-compiler
description: Analyze your agent's decision patterns and compile them into deterministic graphs. Eliminates LLM calls for repetitive decisions — cutting costs by up to 75%.
version: 0.2.0
author: ybj91
tags:
  - optimization
  - cost-reduction
  - compilation
  - decision-graph
  - deterministic
---

# DSC Compiler — Compile Repetitive Decisions

Stop paying your LLM to answer the same question twice. This skill analyzes your agent's decision history, identifies repeating patterns, and compiles them into deterministic decision graphs that execute in <1ms with zero API calls.

## Commands

### `/dsc-analyze` — Analyze Decision Patterns

Analyze recent conversation history and execution logs to find compilable patterns.

1. Collect the agent's recent decision history from the session
2. Run the DSC log analyzer:
   ```bash
   dsc analyze logs ./logs/ --output report.json
   ```
3. Present the compilability report showing:
   - Overall score (what % of decisions can be compiled)
   - Each decision pattern found (router, classifier, rules, pipeline)
   - Estimated cost savings (current vs compiled, breakeven point)
4. If score > 50%, recommend running `/dsc-compile`

### `/dsc-compile` — Compile Decision Graphs

Compile the identified patterns into deterministic artifacts.

1. Check for an existing analysis report
2. Initialize a DSC project and create scenarios from the report:
   ```bash
   dsc init "OpenClaw Agent"
   dsc analyze apply report.json <project-id>
   ```
3. For each scenario, simulate traces and compile:
   ```bash
   dsc trace simulate <project-id> <scenario-id> input.json
   dsc extract <project-id> <scenario-id>
   dsc optimize <project-id> <scenario-id>
   dsc compile <project-id> <scenario-id>
   ```
4. Export the compiled artifacts for the OpenClaw plugin:
   ```bash
   dsc export openclaw <project-id> --output ./compiled/
   ```
5. Report results: states, transitions, estimated savings

### `/dsc-status` — Check Compiled Paths

Show which decision paths are currently compiled and running deterministically.

Check the compiled artifacts directory and report:
- Active compiled scenarios and their stats
- How many decisions were handled by compiled paths vs LLM
- Cumulative cost savings since compilation

## How It Works

```
Incoming Message
      │
      ▼
┌─────────────┐     ┌──────────────┐
│ DSC Compiled │ ──► │ Instant Reply │  <1ms, $0
│ Graph Match? │     │ (no LLM)     │
└──────┬──────┘     └──────────────┘
       │ no match
       ▼
┌─────────────┐     ┌──────────────┐
│ Normal LLM  │ ──► │ LLM Response  │  500ms, $0.01
│ Processing   │     │              │
└─────────────┘     └──────────────┘
```

## Requirements

- Python 3.11+ with DSC installed (`pip install dsc`)
- Anthropic API key (for compilation only — runtime is free)

## Links

- [DSC GitHub](https://github.com/ybj91/decision-structure-compiler)
- [Integration Guide](https://github.com/ybj91/decision-structure-compiler/blob/main/openclaw/README.md)
