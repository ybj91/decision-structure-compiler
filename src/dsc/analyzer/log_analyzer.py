"""Log-based analysis to detect compilable patterns from agent execution logs.

Parses execution logs in various formats, clusters similar executions,
and uses an LLM to identify repeating decision patterns.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dsc.analyzer.report import (
    Compilability,
    CompilabilityReport,
    DecisionPoint,
    SuggestedScenario,
)


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse JSON Lines log file."""
    entries = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def parse_json_array(path: Path) -> list[dict[str, Any]]:
    """Parse a JSON file containing an array of log entries."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "entries" in data:
        return data["entries"]
    if isinstance(data, dict) and "logs" in data:
        return data["logs"]
    return [data]


def load_logs(path: Path, format: str = "auto") -> list[dict[str, Any]]:
    """Load log entries from a file or directory.

    Supported formats: jsonl, json, auto (detect from extension).
    """
    if path.is_dir():
        entries = []
        for f in sorted(path.iterdir()):
            if f.suffix in (".jsonl", ".json", ".log"):
                entries.extend(load_logs(f, format))
        return entries

    if format == "auto":
        format = "jsonl" if path.suffix == ".jsonl" else "json"

    if format == "jsonl":
        return parse_jsonl(path)
    return parse_json_array(path)


def summarize_logs(entries: list[dict[str, Any]], max_entries: int = 100) -> dict[str, Any]:
    """Summarize log entries for LLM analysis.

    Extracts key patterns without sending all raw data.
    """
    # Sample if too many
    if len(entries) > max_entries:
        step = len(entries) // max_entries
        sampled = entries[::step][:max_entries]
    else:
        sampled = entries

    # Try to detect common log shapes
    all_keys: dict[str, int] = {}
    actions_seen: dict[str, int] = {}
    states_seen: dict[str, int] = {}
    inputs_keys: dict[str, int] = {}

    for entry in entries:
        for key in entry:
            all_keys[key] = all_keys.get(key, 0) + 1

        # Try common field names for actions/tools
        for action_key in ("action", "tool", "function", "tool_name", "function_name", "name"):
            if action_key in entry:
                val = str(entry[action_key])
                actions_seen[val] = actions_seen.get(val, 0) + 1

        # Try common field names for states
        for state_key in ("state", "status", "step", "stage", "phase"):
            if state_key in entry:
                val = str(entry[state_key])
                states_seen[val] = states_seen.get(val, 0) + 1

        # Try to find input/observation fields
        for input_key in ("input", "observation", "request", "query", "params", "args"):
            if input_key in entry and isinstance(entry[input_key], dict):
                for k in entry[input_key]:
                    inputs_keys[k] = inputs_keys.get(k, 0) + 1

    return {
        "total_entries": len(entries),
        "sampled_entries": len(sampled),
        "field_names": dict(sorted(all_keys.items(), key=lambda x: -x[1])),
        "actions_seen": dict(sorted(actions_seen.items(), key=lambda x: -x[1])),
        "states_seen": dict(sorted(states_seen.items(), key=lambda x: -x[1])),
        "input_fields": dict(sorted(inputs_keys.items(), key=lambda x: -x[1])),
        "sample_entries": sampled[:20],
    }


# ── LLM analysis schema ──────────────────────────────────────

ANALYZE_LOGS_SCHEMA = {
    "type": "object",
    "properties": {
        "decision_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "compilability": {"type": "string", "enum": ["compilable", "partially_compilable", "not_compilable"]},
                    "reason": {"type": "string"},
                    "pattern": {"type": "string"},
                    "determinism_ratio": {"type": "number", "description": "0-1: how consistently the same input produces the same output"},
                },
                "required": ["name", "description", "compilability", "reason", "pattern"],
            },
        },
        "suggested_scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "states": {"type": "array", "items": {"type": "string"}},
                    "actions": {"type": "array", "items": {"type": "string"}},
                    "observation_fields": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "description", "states", "actions", "observation_fields", "confidence"],
            },
        },
        "overall_score": {"type": "number"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision_points", "suggested_scenarios", "overall_score"],
}


class LogAnalyzer:
    """Analyze agent execution logs for compilable decision patterns."""

    def __init__(self, llm_client: Any) -> None:
        self.llm = llm_client

    def analyze(self, log_path: Path, format: str = "auto") -> CompilabilityReport:
        """Analyze execution logs and return a compilability report."""
        entries = load_logs(log_path, format)

        if not entries:
            return CompilabilityReport(
                source_type="logs",
                overall_score=0.0,
                warnings=["No log entries found."],
            )

        summary = summarize_logs(entries)

        system = (
            "You are an AI agent compilability analyst. You analyze execution logs from LLM-powered agents "
            "to determine which decision patterns repeat consistently and could be compiled into "
            "deterministic decision graphs.\n\n"
            "DSC compiles: (State + Condition) -> (Action, Next State)\n\n"
            "What to look for in logs:\n"
            "- Repeating action sequences (same input type -> same action) -> COMPILABLE\n"
            "- Finite set of states/stages that executions pass through -> COMPILABLE\n"
            "- Consistent routing by input category/type -> COMPILABLE\n"
            "- Rule-based decisions (thresholds, comparisons) -> COMPILABLE\n"
            "- Highly variable outputs for similar inputs -> NOT COMPILABLE\n"
            "- Free-form text generation -> NOT COMPILABLE\n\n"
            "Key metric: determinism_ratio = (times same input -> same output) / (total occurrences)\n"
            "If ratio > 0.9, it's likely compilable.\n\n"
            "Analyze the log summary and identify compilable patterns."
        )

        user_msg = (
            f"## Log Summary\n```json\n{json.dumps(summary, indent=2, default=str)}\n```\n\n"
            "Analyze these execution logs. Identify:\n"
            "1. Repeating decision patterns and their determinism\n"
            "2. Compilable scenarios with states, actions, and observation fields\n"
            "3. Overall compilability score\n"
            "4. Any warnings about non-deterministic behavior"
        )

        result = self.llm.structured_request(
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            tool_name="analyze_logs",
            tool_schema=ANALYZE_LOGS_SCHEMA,
            tool_description="Report the compilability analysis of the agent logs",
        )

        return self._build_report(result, summary)

    def _build_report(self, result: dict, summary: dict) -> CompilabilityReport:
        decision_points = []
        for dp in result.get("decision_points", []):
            decision_points.append(DecisionPoint(
                name=dp["name"],
                description=dp["description"],
                compilability=Compilability(dp["compilability"]),
                reason=dp["reason"],
                pattern=dp.get("pattern", ""),
            ))

        scenarios = []
        for sc in result.get("suggested_scenarios", []):
            scenarios.append(SuggestedScenario(
                name=sc["name"],
                description=sc["description"],
                states=sc.get("states", []),
                actions=sc.get("actions", []),
                observation_fields=sc.get("observation_fields", []),
                confidence=sc.get("confidence", 0.5),
                source="log_analysis",
            ))

        compilable = sum(1 for dp in decision_points if dp.compilability == Compilability.COMPILABLE)
        partial = sum(1 for dp in decision_points if dp.compilability == Compilability.PARTIALLY_COMPILABLE)
        not_comp = sum(1 for dp in decision_points if dp.compilability == Compilability.NOT_COMPILABLE)

        return CompilabilityReport(
            source_type="logs",
            overall_score=result.get("overall_score", 0.0),
            total_decision_points=len(decision_points),
            compilable_points=compilable,
            partially_compilable_points=partial,
            not_compilable_points=not_comp,
            decision_points=decision_points,
            scenarios=scenarios,
            warnings=result.get("warnings", []),
            raw_analysis={"log_summary": summary},
        )
