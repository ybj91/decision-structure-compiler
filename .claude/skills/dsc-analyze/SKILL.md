---
name: dsc-analyze
description: Analyze the current codebase or agent code for compilable decision patterns. Shows compilability score, decision points, suggested DSC scenarios, and cost savings estimate.
---

# DSC Analyze

Analyze agent code in this workspace to determine what can be compiled into deterministic decision graphs.

## Step 0: Ensure DSC is available

Before doing anything else, check if DSC is installed and install it if needed:

```bash
python -c "import dsc" 2>/dev/null || pip install -e ".[dev]" 2>/dev/null || pip install git+https://github.com/ybj91/decision-structure-compiler.git
```

If the workspace IS the DSC repo itself (check for `src/dsc/`), use `pip install -e ".[dev]"`.
If not, install from GitHub. This is a one-time setup.

Verify it works:
```bash
dsc --help
```

## Step 1: Find agent code

If `$ARGUMENTS` is provided, use that path. Otherwise, search the workspace for Python files with decision logic:

- Files with `route`, `handle`, `dispatch`, `classify`, `decide` in function names
- Files with `if/elif` chains or `match` statements
- Files importing agent frameworks (langchain, crewai, autogen, openclaw, etc.)
- Files with LLM/API calls (`openai`, `anthropic`, `chat`, `complete`)

Use Glob and Grep to find these files. Note the paths.

## Step 2: Run analysis

```bash
dsc analyze code <path-to-agent-code> --output report.json
```

If execution logs exist (`.jsonl`, `.json` files with agent traces), include them:
```bash
dsc analyze code <path-to-agent-code> --logs <path-to-logs> --output report.json
```

## Step 3: Present the report

Format the results clearly:
- **Compilability Score**: X% — what fraction of decisions can be compiled
- **Decision Points**: table of each point, pattern type, and compilability
- **Suggested Scenarios**: DSC scenarios with states, actions, observation fields
- **Cost Estimate**: current vs compiled cost, savings %, breakeven
- **Warnings**: what can't be compiled and why

## Step 4: Recommend next steps

- Score > 50%: recommend `/dsc-compile` to compile the scenarios
- Score < 50%: explain what can't be compiled, suggest restructuring
- Always mention the cost savings potential
