---
name: dsc-compile
description: Run the full DSC compilation pipeline — create project, apply analysis scenarios, simulate traces, extract decision graph, optimize, and compile into a deterministic runtime artifact.
---

# DSC Compile

Run the full DSC pipeline to compile agent decision logic into a deterministic artifact.

## Step 0: Ensure DSC is available

```bash
python -c "import dsc" 2>/dev/null || pip install -e ".[dev]" 2>/dev/null || pip install git+https://github.com/ybj91/decision-structure-compiler.git
```

Verify: `dsc --help`

## Step 1: Check prerequisites

Look for an existing analysis report:
```bash
ls report.json 2>/dev/null || ls *.report.json 2>/dev/null
```
If no report exists, tell the user to run `/dsc-analyze` first and stop.

## Step 2: Initialize project and create scenarios

```bash
dsc init "Compiled Agent"
```
Note the project ID. Then apply the analysis report:
```bash
dsc analyze apply report.json <project-id>
```
Note the scenario IDs from the output.

## Step 3: Simulate traces

For each scenario, create 3-5 diverse test input JSON files that cover different paths (happy path, edge cases, fallbacks). The inputs should match the scenario's observation schema.

Write each input file, then simulate:
```bash
dsc trace simulate <project-id> <scenario-id> input1.json
dsc trace simulate <project-id> <scenario-id> input2.json
dsc trace simulate <project-id> <scenario-id> input3.json
```

## Step 4: Extract, optimize, compile

For each scenario:
```bash
dsc extract <project-id> <scenario-id>
dsc optimize <project-id> <scenario-id>
dsc compile <project-id> <scenario-id>
```

## Step 5: Report results

Tell the user:
- States and transitions in the compiled graph
- Where the artifact is saved (`.dsc_data/projects/<id>/scenarios/<id>/compiled/`)
- They can test with `/dsc-run`
- If using OpenClaw, export with `dsc export openclaw <project-id> --output ./compiled/`

## Notes

- Steps 3-4 require `ANTHROPIC_API_KEY` to be set
- If any step fails, diagnose the error and fix before continuing
