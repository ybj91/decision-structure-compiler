---
name: dsc-compile
description: Run the full DSC compilation pipeline — create project, apply analysis scenarios, simulate traces, extract decision graph, optimize, and compile into a deterministic runtime artifact.
---

# DSC Compile

Run the full DSC pipeline to compile agent decision logic into a deterministic artifact.

## Steps

### 1. Check prerequisites

Look for an existing analysis report:
```bash
ls report.json 2>/dev/null || ls *.report.json 2>/dev/null
```
If no report exists, tell the user to run `/dsc-analyze` first.

### 2. Initialize project

```bash
dsc init "Project Name"
```
Note the project ID from the output.

### 3. Create scenarios from analysis

```bash
dsc analyze apply report.json <project-id>
```
This creates DSC scenarios from the analysis report. Note the scenario IDs.

### 4. Simulate traces

For each scenario, create test input files and simulate traces. Generate 3-5 diverse test inputs that cover different paths:

```bash
dsc trace simulate <project-id> <scenario-id> input1.json
dsc trace simulate <project-id> <scenario-id> input2.json
dsc trace simulate <project-id> <scenario-id> input3.json
```

The test inputs should be JSON files matching the scenario's observation schema. Create inputs that exercise different branches — happy path, edge cases, fallbacks.

### 5. Extract decision graph

```bash
dsc extract <project-id> <scenario-id>
```
This runs the 3-phase LLM pipeline: extract transitions → normalize states → formalize conditions.

### 6. Optimize

```bash
dsc optimize <project-id> <scenario-id>
```
Prunes unreachable states, merges duplicates, detects conflicts.

### 7. Compile artifact

```bash
dsc compile <project-id> <scenario-id>
```
Outputs a versioned, self-contained JSON artifact.

### 8. Report results

Tell the user:
- How many states and transitions in the compiled graph
- Where the artifact is saved
- That they can test it with `/dsc-run`

## Arguments

- `$ARGUMENTS` — optional path to report.json. If not provided, look for report.json in the workspace.

## Notes

- Steps 4-7 require an Anthropic API key (set `ANTHROPIC_API_KEY` environment variable)
- Steps 4-6 use the LLM — this is the compile-time cost. After this, runtime is free.
- If any step fails, diagnose the error and suggest fixes before continuing
- The compiled artifact is at `.dsc_data/projects/<id>/scenarios/<id>/compiled/v<n>.json`
