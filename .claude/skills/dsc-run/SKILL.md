---
name: dsc-run
description: Load a compiled DSC artifact and execute it against test inputs to verify deterministic behavior. Shows step-by-step state transitions with zero LLM calls.
---

# DSC Run

Test a compiled DSC artifact by running it against test inputs. Demonstrates deterministic execution with zero LLM calls.

## Steps

### 1. Find the compiled artifact

Look for compiled artifacts in the workspace:
```bash
find .dsc_data -name "*.json" -path "*/compiled/*" 2>/dev/null
```
If `$ARGUMENTS` is provided, use it as the artifact path.

If no artifact found, tell the user to run `/dsc-compile` first.

### 2. Inspect the artifact

Read the compiled artifact to understand:
- What states exist (especially the initial and terminal states)
- What observation fields the conditions check
- What actions are available

Summarize this for the user in a clear format.

### 3. Create test inputs

Based on the artifact's observation schema, create test JSON inputs that exercise different paths. Cover:
- **Happy path**: typical input that follows the main flow
- **Edge case**: boundary values, unusual combinations
- **Fallback**: input that doesn't match any specific condition (triggers default/escalation)

### 4. Run the artifact

Use the DSC CLI to run interactively, or use Python:

```python
from dsc.compiler.compiler import CompiledArtifact
from dsc.runtime.engine import RuntimeEngine

artifact = CompiledArtifact.from_json(open("<artifact-path>").read())
engine = RuntimeEngine.from_artifact(artifact)
engine.start()

# Step through with each test observation
result = engine.step({"field": "value", ...})
print(f"{result.from_state} -> [{result.action}] -> {result.to_state}")
```

Or use the CLI:
```bash
dsc run <artifact-path>
```

### 5. Present results

For each test input, show:
- The state transitions taken: `[state] + {observation} → action → [next_state]`
- Total steps to reach terminal state
- That **zero LLM calls** were made

Compare different inputs side by side to demonstrate the deterministic behavior — same input always produces the same output.

### 6. Validate

Confirm with the user:
- Do the transitions make sense for the domain?
- Are edge cases handled correctly?
- Should any paths be refined? (If so, suggest re-running `/dsc-compile` with more test traces)

## Arguments

- `$ARGUMENTS` — optional path to compiled artifact JSON. If not provided, search the workspace.

## Notes

- No API key needed — runtime execution is fully deterministic
- No network calls — the artifact is self-contained
- Sub-millisecond per step — no latency
