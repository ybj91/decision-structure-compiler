# DSC + OpenClaw Integration Guide

> Stop paying your LLM to answer the same question twice.

This guide shows how to integrate DSC (Decision Structure Compiler) with [OpenClaw](https://github.com/openclaw/openclaw) to automatically compile repetitive agent decisions into deterministic graphs — cutting LLM costs by up to 75%.

## The Problem

OpenClaw agents call the LLM on every message. But most agents handle the same types of decisions repeatedly:

- "I want a refund" → check amount → approve or escalate
- "What's my balance?" → look up billing → respond
- "My service is down" → check status → notify

Each of these burns ~2,000 tokens ($0.006-0.03) per execution. At scale, this adds up fast — $200-600/month for active agents.

## The Solution

DSC analyzes your agent's decision history, identifies the repeating patterns, and compiles them into deterministic graphs. Compiled decisions execute in **<1ms with zero LLM calls**. Novel inputs still go through the LLM normally.

```
Before:  Every message → LLM ($0.01, 500ms)
After:   Compiled match → Instant ($0, <1ms)
         No match       → LLM ($0.01, 500ms)
```

## Quick Start

### 1. Install DSC

```bash
pip install dsc
```

### 2. Analyze Your Agent

Point DSC at your OpenClaw agent's code or execution logs:

```bash
# Analyze source code
dsc analyze code ./my-openclaw-agent/ --output report.json

# Or analyze execution logs (if you have them)
dsc analyze logs ./logs/ --output report.json

# Or both for higher confidence
dsc analyze code ./my-openclaw-agent/ --logs ./logs/ --output report.json
```

You'll get a report like:

```
Compilability Score: ████████████████░░░░ 78%

  Total decision points: 6
  Compilable:            4
  Partially compilable:  1
  Not compilable:        1

  Suggested DSC Scenarios (2):
    refund_routing (confidence: 92%)
    ticket_triage (confidence: 85%)

  Cost Estimate:
    Current:    $18.00 / 1K executions
    Compiled:   $4.50 / 1K executions
    Savings:    75%
    Breakeven:  47 executions
```

### 3. Compile

```bash
# Create project and scenarios from the report
dsc init "My OpenClaw Agent"
dsc analyze apply report.json <project-id>

# Simulate traces, extract, optimize, compile
dsc trace simulate <project-id> <scenario-id> test_input.json
dsc extract <project-id> <scenario-id>
dsc optimize <project-id> <scenario-id>
dsc compile <project-id> <scenario-id>

# Export for OpenClaw plugin
dsc export openclaw <project-id> --output ./compiled/
```

### 4. Install the Plugin

Copy the `openclaw/plugin/` directory into your OpenClaw setup and enable it:

```json
// openclaw.plugin.json
{
  "name": "dsc-compiler",
  "type": "context-engine",
  "config": {
    "artifactsDir": "./compiled",
    "enabled": true,
    "fallbackToLLM": true
  }
}
```

### 5. Done

Your agent now runs a hybrid model:

| Input | Route | Latency | Cost |
|---|---|---|---|
| "I want a refund for $45" | Compiled graph | <1ms | $0 |
| "Check my billing" | Compiled graph | <1ms | $0 |
| "Write me a poem about lobsters" | LLM (novel input) | ~500ms | ~$0.01 |

## Architecture

```
                   Incoming Message
                         │
                         ▼
              ┌─────────────────────┐
              │   OpenClaw Agent    │
              │                     │
              │  ┌───────────────┐  │
              │  │ ContextEngine │  │
              │  │               │  │
              │  │  ┌─────────┐  │  │
              │  │  │   DSC   │  │  │
              │  │  │ Plugin  │  │  │
              │  │  └────┬────┘  │  │
              │  └───────┼───────┘  │
              └──────────┼──────────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
        Match found   No match     │
              │          │          │
              ▼          ▼          │
      ┌──────────┐ ┌──────────┐    │
      │   DSC    │ │   LLM    │    │
      │ Runtime  │ │  Call    │    │
      │ (<1ms)   │ │ (~500ms) │    │
      └────┬─────┘ └────┬─────┘    │
           │             │          │
           └──────┬──────┘          │
                  │                 │
                  ▼                 │
              Response              │
```

## The ContextEngine Plugin

The DSC plugin hooks into OpenClaw's ContextEngine lifecycle:

**`beforeModelCall`** — Called before every LLM request. The plugin:
1. Extracts structured observations from the message (intent, amounts, IDs)
2. Checks all compiled artifacts for a matching transition
3. If match: intercepts the call, returns the deterministic action (0 tokens)
4. If no match: passes through to the LLM normally

**Hot reload** — Artifacts are watched for changes. Recompile and the plugin picks up new graphs automatically.

**Stats tracking** — The plugin tracks compiled hits vs LLM fallbacks, so you can measure real savings.

## OpenClaw Skill Commands

If you install the DSC skill from ClawHub:

```
/dsc-analyze    Analyze your agent's decision patterns
/dsc-compile    Compile identified patterns into graphs
/dsc-status     Show compiled paths and savings stats
```

## FAQ

**Does this change how my agent responds?**
No. Compiled paths produce the exact same actions the LLM would. The decision logic is extracted from actual LLM traces.

**What if my decisions change?**
Recompile. The pipeline is designed for iteration: analyze → compile → deploy → analyze again.

**What can't be compiled?**
Free-form text generation, open-ended conversations, creative tasks. DSC targets the structured decision layer, not the generative layer.

**Is it safe?**
Every compiled graph is inspectable and auditable. You can review exactly which conditions produce which actions before deploying.
