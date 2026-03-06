"""Static analysis of agent source code to detect compilable patterns.

Parses Python source files using the ast module to extract decision structure,
then uses an LLM to classify each component's compilability.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from dsc.analyzer.report import (
    Compilability,
    CompilabilityReport,
    DecisionPoint,
    SuggestedScenario,
)


class CodeStructure(ast.NodeVisitor):
    """Extract decision-relevant structure from Python AST."""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.conditionals: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.string_literals: list[str] = []
        self._current_func: str | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        old_func = self._current_func
        self._current_func = node.name
        self.functions.append({
            "name": node.name,
            "line": node.lineno,
            "args": [a.arg for a in node.args.args],
            "decorators": [self._decorator_name(d) for d in node.decorator_list],
            "docstring": ast.get_docstring(node) or "",
        })
        self.generic_visit(node)
        self._current_func = old_func

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(self._attr_path(base))
        self.classes.append({
            "name": node.name,
            "line": node.lineno,
            "bases": bases,
            "docstring": ast.get_docstring(node) or "",
        })
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.conditionals.append({
            "line": node.lineno,
            "function": self._current_func or "(module)",
            "test": ast.dump(node.test),
            "has_elif": len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If),
            "branch_count": self._count_branches(node),
        })
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.conditionals.append({
            "line": node.lineno,
            "function": self._current_func or "(module)",
            "test": "match_statement",
            "has_elif": False,
            "branch_count": len(node.cases),
        })
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = self._call_name(node)
        if name and any(kw in name.lower() for kw in (
            "tool", "invoke", "call", "run", "execute", "dispatch",
            "create", "send", "chat", "complete", "generate",
        )):
            self.tool_calls.append({
                "name": name,
                "line": node.lineno,
                "function": self._current_func or "(module)",
            })
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and len(node.value) > 20:
            self.string_literals.append(node.value[:200])
        self.generic_visit(node)

    def _decorator_name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Call):
            return self._call_name(node) or ""
        if isinstance(node, ast.Attribute):
            return self._attr_path(node)
        return ""

    def _call_name(self, node: ast.Call) -> str | None:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return self._attr_path(node.func)
        return None

    def _attr_path(self, node: ast.Attribute) -> str:
        parts = [node.attr]
        current = node.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def _count_branches(self, node: ast.If) -> int:
        count = 1
        for child in node.orelse:
            if isinstance(child, ast.If):
                count += self._count_branches(child)
            else:
                count += 1
                break
        return count


def extract_code_structure(source_path: Path) -> dict[str, Any]:
    """Extract decision-relevant structure from Python source files.

    Accepts a file or directory. Returns a summary dict.
    """
    files_structure = []

    if source_path.is_file():
        py_files = [source_path]
    else:
        py_files = sorted(source_path.rglob("*.py"))

    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        visitor = CodeStructure(str(py_file))
        visitor.visit(tree)

        # Only include files with decision-relevant content
        if visitor.functions or visitor.conditionals or visitor.tool_calls:
            files_structure.append({
                "file": str(py_file),
                "functions": visitor.functions,
                "classes": visitor.classes,
                "conditionals": visitor.conditionals,
                "tool_calls": visitor.tool_calls,
                "prompt_fragments": [s for s in visitor.string_literals
                                     if any(kw in s.lower() for kw in ("you are", "system", "assistant", "classify", "route", "decide"))],
            })

    return {
        "files_analyzed": len(py_files),
        "files_with_decisions": len(files_structure),
        "files": files_structure,
    }


# ── LLM analysis schemas ─────────────────────────────────────

ANALYZE_CODE_SCHEMA = {
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
                    "pattern": {"type": "string", "description": "Pattern type: router, classifier, pipeline, rules, generator, conversation, dynamic"},
                    "source_location": {"type": "string"},
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
        "overall_score": {"type": "number", "description": "0.0-1.0 compilability score"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision_points", "suggested_scenarios", "overall_score"],
}


class StaticAnalyzer:
    """Analyze agent source code for compilable decision patterns."""

    def __init__(self, llm_client: Any) -> None:
        self.llm = llm_client

    def analyze(self, source_path: Path) -> CompilabilityReport:
        """Analyze Python source code and return a compilability report."""
        structure = extract_code_structure(source_path)

        if structure["files_with_decisions"] == 0:
            return CompilabilityReport(
                source_type="code",
                overall_score=0.0,
                warnings=["No decision-relevant code found in the provided path."],
            )

        system = (
            "You are an AI agent compilability analyst. You analyze Python agent source code to determine "
            "which parts can be compiled into deterministic decision graphs (state machines) using DSC "
            "(Decision Structure Compiler).\n\n"
            "DSC compiles decision logic into: (State + Condition) -> (Action, Next State)\n\n"
            "Compilable patterns:\n"
            "- Router/dispatcher: routes by type, intent, category -> COMPILABLE\n"
            "- Classifier -> action: LLM classifies then takes fixed action -> COMPILABLE\n"
            "- Sequential pipeline: check A then B then C -> COMPILABLE\n"
            "- Rule-based branching: if amount > 100, if status == 'active' -> COMPILABLE\n"
            "- Retry/fallback: try A, if fail try B -> COMPILABLE\n"
            "- Threshold routing: score > 0.8 -> reject, > 0.5 -> review -> COMPILABLE\n\n"
            "Non-compilable patterns:\n"
            "- Free-form text generation (writing, summarizing) -> NOT COMPILABLE\n"
            "- Open-ended multi-turn conversation -> NOT COMPILABLE\n"
            "- Dynamic tool construction at runtime -> NOT COMPILABLE\n"
            "- Tasks requiring real-time external knowledge -> NOT COMPILABLE\n\n"
            "Partially compilable: has a compilable routing/decision core but some branches "
            "need LLM for content generation.\n\n"
            "Analyze the code structure and identify all decision points."
        )

        user_msg = (
            f"## Code Structure Analysis\n```json\n{json.dumps(structure, indent=2, default=str)}\n```\n\n"
            "Analyze this agent code. For each decision point:\n"
            "1. Classify its compilability\n"
            "2. Identify the pattern type\n"
            "3. Suggest DSC scenarios for compilable parts\n"
            "4. Provide an overall compilability score"
        )

        result = self.llm.structured_request(
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            tool_name="analyze_code",
            tool_schema=ANALYZE_CODE_SCHEMA,
            tool_description="Report the compilability analysis of the agent code",
        )

        return self._build_report(result, structure)

    def _build_report(self, result: dict, structure: dict) -> CompilabilityReport:
        decision_points = []
        for dp in result.get("decision_points", []):
            decision_points.append(DecisionPoint(
                name=dp["name"],
                description=dp["description"],
                compilability=Compilability(dp["compilability"]),
                reason=dp["reason"],
                pattern=dp.get("pattern", ""),
                source_location=dp.get("source_location", ""),
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
                source="static_analysis",
            ))

        compilable = sum(1 for dp in decision_points if dp.compilability == Compilability.COMPILABLE)
        partial = sum(1 for dp in decision_points if dp.compilability == Compilability.PARTIALLY_COMPILABLE)
        not_comp = sum(1 for dp in decision_points if dp.compilability == Compilability.NOT_COMPILABLE)

        return CompilabilityReport(
            source_type="code",
            overall_score=result.get("overall_score", 0.0),
            total_decision_points=len(decision_points),
            compilable_points=compilable,
            partially_compilable_points=partial,
            not_compilable_points=not_comp,
            decision_points=decision_points,
            scenarios=scenarios,
            warnings=result.get("warnings", []),
            raw_analysis={"code_structure": structure},
        )
