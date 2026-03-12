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

Stop paying your LLM to answer the same question twice.

## Auto-Setup

Before running any command, ensure DSC is installed. Run this once:

```bash
pip install git+https://github.com/ybj91/decision-structure-compiler.git 2>/dev/null && echo "DSC ready" || echo "DSC already installed"
```

Or for full OpenClaw plugin setup (one command):
```bash
curl -sSL https://raw.githubusercontent.com/ybj91/decision-structure-compiler/main/openclaw/setup.sh | bash
```

## Commands

### `/dsc-analyze` — Analyze Decision Patterns

```bash
dsc analyze logs ./logs/ --output report.json
```

If agent source code is available:
```bash
dsc analyze code ./agent/ --logs ./logs/ --output report.json
```

Shows: compilability score, decision patterns, cost savings estimate.

### `/dsc-compile` — Compile Decision Graphs

```bash
dsc init "My Agent"
dsc analyze apply report.json <project-id>
dsc trace simulate <project-id> <scenario-id> input.json
dsc extract <project-id> <scenario-id>
dsc optimize <project-id> <scenario-id>
dsc compile <project-id> <scenario-id>
dsc export openclaw <project-id> --output ./compiled/
```

### `/dsc-status` — Check Compiled Paths

```bash
ls -la ./compiled/*.json 2>/dev/null && echo "Compiled artifacts found" || echo "No compiled artifacts"
```

## How It Works

```
Incoming Message → DSC Plugin → Compiled match? → Instant ($0, <1ms)
                              → No match?       → LLM call ($0.01, 500ms)
```

## Links

- [GitHub](https://github.com/ybj91/decision-structure-compiler)
- [Integration Guide](https://github.com/ybj91/decision-structure-compiler/blob/main/openclaw/README.md)
