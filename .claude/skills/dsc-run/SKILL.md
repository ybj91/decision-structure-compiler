---
name: dsc-run
description: Load a compiled DSC artifact and execute it against test inputs to verify deterministic behavior. Shows step-by-step state transitions with zero LLM calls.
---

# DSC Run

Test a compiled DSC artifact by running test inputs through it. Zero LLM calls.

## Step 0: Ensure DSC is available

```bash
python -c "import dsc" 2>/dev/null || pip install -e ".[dev]" 2>/dev/null || pip install git+https://github.com/ybj91/decision-structure-compiler.git
```

## Step 1: Find the artifact

If `$ARGUMENTS` is provided, use it as the artifact path. Otherwise search:
```bash
find .dsc_data -name "*.json" -path "*/compiled/*" 2>/dev/null
```
Also check `./compiled/` directory. If nothing found, tell the user to run `/dsc-compile` first.

## Step 2: Inspect the artifact

Read the compiled JSON artifact. Summarize for the user:
- States (initial and terminal)
- Observation fields the conditions check
- Available actions

## Step 3: Create and run test inputs

Based on the artifact's schema, create test inputs covering happy path, edge cases, and fallbacks. Run them using Python directly (no API key needed):

```python
import json, sys
sys.path.insert(0, "src")
from dsc.compiler.compiler import CompiledArtifact
from dsc.runtime.engine import RuntimeEngine

artifact = CompiledArtifact.from_json(open("<artifact-path>").read())
engine = RuntimeEngine.from_artifact(artifact)
engine.start()

# Test each observation
for obs in [<test inputs>]:
    if engine.is_terminal:
        break
    result = engine.step(obs)
    print(f"  [{result.from_state}] + {obs}")
    print(f"    → {result.action} → [{result.to_state}]")

print(f"\nReached: {engine.current_state} in {engine.step_count} steps")
print("LLM calls: 0")
```

## Step 4: Present results

For each test input show the state transitions. Compare different inputs side by side to demonstrate deterministic behavior. Confirm with the user that the transitions make sense.
