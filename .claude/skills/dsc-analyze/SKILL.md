---
name: dsc-analyze
description: Analyze the current codebase or agent code for compilable decision patterns. Shows compilability score, decision points, suggested DSC scenarios, and cost savings estimate.
---

# DSC Analyze

Analyze agent code in this workspace to determine what can be compiled into deterministic decision graphs.

## Steps

1. **Find agent code**: Look for Python files that contain decision logic — routers, classifiers, if/elif chains, tool dispatch, approval workflows. Use Glob and Grep to find relevant files. Common patterns:
   - Files with `route`, `handle`, `dispatch`, `classify`, `decide` in function names
   - Files with `if/elif` chains or `match` statements
   - Files importing agent frameworks (langchain, crewai, autogen, etc.)
   - Files with LLM/API calls (`openai`, `anthropic`, `chat`, `complete`)

2. **Run static analysis**: Execute the DSC analyzer on the discovered code:
   ```bash
   dsc analyze code <path-to-agent-code> --output report.json
   ```
   If there are also execution logs available (`.jsonl`, `.json` files with agent traces), include them:
   ```bash
   dsc analyze code <path-to-agent-code> --logs <path-to-logs> --output report.json
   ```

3. **Present the report** clearly to the user:
   - **Compilability Score**: X% — what fraction of decisions can be compiled
   - **Decision Points**: table of each identified point, its pattern type (router/classifier/rules/pipeline), and whether it's compilable
   - **Suggested Scenarios**: the DSC scenarios that could be created, with states, actions, and observation fields
   - **Cost Estimate**: current cost vs compiled cost per 1K executions, savings %, breakeven point
   - **Warnings**: anything that can't be compiled and why

4. **Recommend next steps**:
   - If score > 0.5: recommend running `/dsc-compile` to compile the identified scenarios
   - If score < 0.5: explain what parts can't be compiled and suggest restructuring
   - Always mention the cost savings potential

## Arguments

- `$ARGUMENTS` — optional path to analyze. If not provided, analyze the current workspace.

## Notes

- No API key needed for the analysis itself (uses the current Claude session)
- The analysis uses Python's `ast` module for code parsing — no code is executed
- Log analysis supports JSONL, JSON array, and directory of log files
