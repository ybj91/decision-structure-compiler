"""Tests for the compilability analyzer."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dsc.analyzer.bridge import scenario_from_suggestion, scenarios_from_report
from dsc.analyzer.cost_estimator import estimate_costs
from dsc.analyzer.log_analyzer import LogAnalyzer, load_logs, summarize_logs
from dsc.analyzer.report import (
    Compilability,
    CompilabilityReport,
    CostEstimate,
    DecisionPoint,
    SuggestedScenario,
)
from dsc.analyzer.static_analyzer import StaticAnalyzer, extract_code_structure


# ── Report Models ────────────────────────────────────────────


class TestReportModels:
    def test_decision_point_creation(self):
        dp = DecisionPoint(
            name="route_by_intent",
            description="Routes requests by intent type",
            compilability=Compilability.COMPILABLE,
            reason="Finite set of intents with fixed routing",
            pattern="router",
        )
        assert dp.compilability == Compilability.COMPILABLE
        assert dp.pattern == "router"

    def test_suggested_scenario(self):
        sc = SuggestedScenario(
            name="intent_routing",
            description="Route by customer intent",
            states=["triage", "billing", "resolved"],
            actions=["route_billing", "close_ticket"],
            observation_fields=["intent", "severity"],
            confidence=0.85,
        )
        assert sc.confidence == 0.85
        assert len(sc.states) == 3

    def test_report_serialization_roundtrip(self):
        report = CompilabilityReport(
            source_type="code",
            overall_score=0.75,
            total_decision_points=4,
            compilable_points=3,
            not_compilable_points=1,
            decision_points=[
                DecisionPoint(
                    name="test",
                    description="test",
                    compilability=Compilability.COMPILABLE,
                    reason="test",
                ),
            ],
        )
        json_str = report.model_dump_json()
        restored = CompilabilityReport.model_validate_json(json_str)
        assert restored.overall_score == 0.75
        assert restored.compilable_points == 3
        assert len(restored.decision_points) == 1

    def test_compilability_enum_values(self):
        assert Compilability.COMPILABLE.value == "compilable"
        assert Compilability.PARTIALLY_COMPILABLE.value == "partially_compilable"
        assert Compilability.NOT_COMPILABLE.value == "not_compilable"


# ── Static Analyzer ──────────────────────────────────────────


SAMPLE_AGENT_CODE = '''\
"""A simple support routing agent."""

from some_framework import Agent, tool

class SupportAgent(Agent):
    """Routes customer support requests."""

    def route(self, request):
        """Route by intent."""
        if request["intent"] == "refund":
            return self.handle_refund(request)
        elif request["intent"] == "billing":
            return self.handle_billing(request)
        elif request["intent"] == "complaint":
            return self.escalate(request)
        else:
            return self.general_inquiry(request)

    def handle_refund(self, request):
        if request["amount"] > 100:
            return self.escalate(request)
        return self.auto_approve(request)

    def handle_billing(self, request):
        result = self.lookup_billing(request["customer_id"])
        return result

    def generate_response(self, context):
        """Generate a free-form response using LLM."""
        return self.llm.chat("You are a helpful agent", context)

    @tool
    def lookup_billing(self, customer_id):
        """Look up billing records."""
        pass

    @tool
    def auto_approve(self, request):
        """Auto-approve a refund."""
        pass

    def escalate(self, request):
        """Escalate to human agent."""
        pass
'''


class TestCodeStructureExtraction:
    def test_extract_from_file(self, tmp_path):
        code_file = tmp_path / "agent.py"
        code_file.write_text(SAMPLE_AGENT_CODE)

        structure = extract_code_structure(code_file)
        assert structure["files_analyzed"] == 1
        assert structure["files_with_decisions"] == 1

        file_data = structure["files"][0]
        assert len(file_data["functions"]) > 0

        func_names = [f["name"] for f in file_data["functions"]]
        assert "route" in func_names
        assert "handle_refund" in func_names

    def test_extract_conditionals(self, tmp_path):
        code_file = tmp_path / "agent.py"
        code_file.write_text(SAMPLE_AGENT_CODE)

        structure = extract_code_structure(code_file)
        file_data = structure["files"][0]

        # Should find if/elif chains
        assert len(file_data["conditionals"]) > 0
        # The main router has 4 branches
        router_cond = [c for c in file_data["conditionals"] if c["branch_count"] >= 3]
        assert len(router_cond) > 0

    def test_extract_from_directory(self, tmp_path):
        (tmp_path / "agent.py").write_text(SAMPLE_AGENT_CODE)
        (tmp_path / "utils.py").write_text("def helper(): pass")

        structure = extract_code_structure(tmp_path)
        assert structure["files_analyzed"] == 2

    def test_extract_empty_directory(self, tmp_path):
        structure = extract_code_structure(tmp_path)
        assert structure["files_analyzed"] == 0
        assert structure["files_with_decisions"] == 0

    def test_extract_handles_syntax_errors(self, tmp_path):
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def broken(:\n  pass")

        structure = extract_code_structure(bad_file)
        assert structure["files_with_decisions"] == 0


MOCK_STATIC_ANALYSIS_RESULT = {
    "decision_points": [
        {
            "name": "route_by_intent",
            "description": "Routes requests by intent type (refund, billing, complaint)",
            "compilability": "compilable",
            "reason": "Finite set of intents with deterministic routing",
            "pattern": "router",
            "source_location": "agent.py:10",
        },
        {
            "name": "refund_threshold",
            "description": "Checks refund amount against $100 threshold",
            "compilability": "compilable",
            "reason": "Simple threshold comparison with two outcomes",
            "pattern": "rules",
            "source_location": "agent.py:22",
        },
        {
            "name": "generate_response",
            "description": "Free-form LLM response generation",
            "compilability": "not_compilable",
            "reason": "Open-ended text generation cannot be compiled",
            "pattern": "generator",
            "source_location": "agent.py:30",
        },
    ],
    "suggested_scenarios": [
        {
            "name": "support_routing",
            "description": "Route customer support requests by intent and apply rules",
            "states": ["triage", "refund_review", "billing_lookup", "escalated", "resolved"],
            "actions": ["auto_approve", "lookup_billing", "escalate"],
            "observation_fields": ["intent", "amount", "customer_id"],
            "confidence": 0.9,
        },
    ],
    "overall_score": 0.65,
    "warnings": ["generate_response() uses free-form LLM — cannot be compiled"],
}


class TestStaticAnalyzer:
    def test_analyze_returns_report(self, tmp_path):
        code_file = tmp_path / "agent.py"
        code_file.write_text(SAMPLE_AGENT_CODE)

        mock_llm = MagicMock()
        mock_llm.structured_request.return_value = MOCK_STATIC_ANALYSIS_RESULT

        analyzer = StaticAnalyzer(mock_llm)
        report = analyzer.analyze(code_file)

        assert report.source_type == "code"
        assert report.overall_score == 0.65
        assert report.total_decision_points == 3
        assert report.compilable_points == 2
        assert report.not_compilable_points == 1
        assert len(report.scenarios) == 1
        assert report.scenarios[0].name == "support_routing"

    def test_analyze_empty_path(self, tmp_path):
        mock_llm = MagicMock()
        analyzer = StaticAnalyzer(mock_llm)
        report = analyzer.analyze(tmp_path)

        assert report.overall_score == 0.0
        assert "No decision-relevant code found" in report.warnings[0]
        mock_llm.structured_request.assert_not_called()


# ── Log Analyzer ─────────────────────────────────────────────


SAMPLE_LOGS = [
    {"action": "classify_intent", "input": {"text": "I want a refund"}, "output": {"intent": "refund"}, "state": "triage"},
    {"action": "check_eligibility", "input": {"intent": "refund", "amount": 45}, "output": {"eligible": True}, "state": "refund_review"},
    {"action": "approve_refund", "input": {"amount": 45}, "output": {"status": "approved"}, "state": "resolved"},
    {"action": "classify_intent", "input": {"text": "Check my bill"}, "output": {"intent": "billing"}, "state": "triage"},
    {"action": "lookup_billing", "input": {"customer_id": "C001"}, "output": {"balance": 120}, "state": "billing_review"},
    {"action": "close_ticket", "input": {}, "output": {"status": "closed"}, "state": "resolved"},
    {"action": "classify_intent", "input": {"text": "Refund my order"}, "output": {"intent": "refund"}, "state": "triage"},
    {"action": "check_eligibility", "input": {"intent": "refund", "amount": 250}, "output": {"eligible": False}, "state": "refund_review"},
    {"action": "escalate", "input": {"reason": "high_value"}, "output": {"ticket": "T-123"}, "state": "escalated"},
]


class TestLogParsing:
    def test_load_jsonl(self, tmp_path):
        log_file = tmp_path / "logs.jsonl"
        log_file.write_text("\n".join(json.dumps(e) for e in SAMPLE_LOGS))

        entries = load_logs(log_file)
        assert len(entries) == 9

    def test_load_json_array(self, tmp_path):
        log_file = tmp_path / "logs.json"
        log_file.write_text(json.dumps(SAMPLE_LOGS))

        entries = load_logs(log_file)
        assert len(entries) == 9

    def test_load_directory(self, tmp_path):
        (tmp_path / "a.jsonl").write_text("\n".join(json.dumps(e) for e in SAMPLE_LOGS[:3]))
        (tmp_path / "b.jsonl").write_text("\n".join(json.dumps(e) for e in SAMPLE_LOGS[3:]))

        entries = load_logs(tmp_path)
        assert len(entries) == 9

    def test_summarize_logs(self):
        summary = summarize_logs(SAMPLE_LOGS)
        assert summary["total_entries"] == 9
        assert "classify_intent" in summary["actions_seen"]
        assert "triage" in summary["states_seen"]
        assert "text" in summary["input_fields"] or "intent" in summary["input_fields"]

    def test_summarize_sampling(self):
        # Large log set should be sampled
        large_logs = SAMPLE_LOGS * 20  # 180 entries
        summary = summarize_logs(large_logs, max_entries=50)
        assert summary["total_entries"] == 180
        assert summary["sampled_entries"] <= 50


MOCK_LOG_ANALYSIS_RESULT = {
    "decision_points": [
        {
            "name": "intent_classification",
            "description": "Classifies customer intent from text",
            "compilability": "compilable",
            "reason": "Consistent mapping from input text patterns to intents",
            "pattern": "classifier",
            "determinism_ratio": 0.95,
        },
        {
            "name": "refund_eligibility",
            "description": "Checks refund eligibility by amount",
            "compilability": "compilable",
            "reason": "Threshold-based decision with consistent outcomes",
            "pattern": "rules",
            "determinism_ratio": 1.0,
        },
    ],
    "suggested_scenarios": [
        {
            "name": "support_ticket_routing",
            "description": "Route and resolve support tickets",
            "states": ["triage", "refund_review", "billing_review", "escalated", "resolved"],
            "actions": ["classify_intent", "check_eligibility", "approve_refund", "lookup_billing", "escalate", "close_ticket"],
            "observation_fields": ["text", "intent", "amount", "customer_id"],
            "confidence": 0.88,
        },
    ],
    "overall_score": 0.85,
    "warnings": [],
}


class TestLogAnalyzer:
    def test_analyze_returns_report(self, tmp_path):
        log_file = tmp_path / "logs.jsonl"
        log_file.write_text("\n".join(json.dumps(e) for e in SAMPLE_LOGS))

        mock_llm = MagicMock()
        mock_llm.structured_request.return_value = MOCK_LOG_ANALYSIS_RESULT

        analyzer = LogAnalyzer(mock_llm)
        report = analyzer.analyze(log_file)

        assert report.source_type == "logs"
        assert report.overall_score == 0.85
        assert report.total_decision_points == 2
        assert report.compilable_points == 2
        assert len(report.scenarios) == 1

    def test_analyze_empty_logs(self, tmp_path):
        log_file = tmp_path / "empty.jsonl"
        log_file.write_text("")

        mock_llm = MagicMock()
        analyzer = LogAnalyzer(mock_llm)
        report = analyzer.analyze(log_file)

        assert report.overall_score == 0.0
        assert "No log entries found" in report.warnings[0]
        mock_llm.structured_request.assert_not_called()


# ── Cost Estimator ───────────────────────────────────────────


class TestCostEstimator:
    def test_basic_estimate(self):
        report = CompilabilityReport(
            source_type="code",
            overall_score=0.8,
            total_decision_points=5,
            compilable_points=4,
            not_compilable_points=1,
            scenarios=[SuggestedScenario(
                name="test", description="test",
                states=["a", "b"], actions=["x"],
                observation_fields=["f"], confidence=0.9,
            )],
        )
        estimate = estimate_costs(report)

        assert estimate.current_cost_per_1k > 0
        assert estimate.compiled_cost_per_1k < estimate.current_cost_per_1k
        assert estimate.savings_percent > 0
        assert estimate.breakeven_executions > 0
        assert estimate.compile_cost > 0

    def test_fully_compilable(self):
        report = CompilabilityReport(
            source_type="code",
            overall_score=1.0,
            total_decision_points=3,
            compilable_points=3,
        )
        estimate = estimate_costs(report)
        assert estimate.compiled_cost_per_1k == 0
        assert estimate.savings_percent == 100.0

    def test_nothing_compilable(self):
        report = CompilabilityReport(
            source_type="code",
            overall_score=0.0,
            total_decision_points=3,
            not_compilable_points=3,
        )
        estimate = estimate_costs(report)
        assert estimate.compiled_cost_per_1k == estimate.current_cost_per_1k
        assert estimate.savings_percent == 0

    def test_empty_report(self):
        report = CompilabilityReport(source_type="code", overall_score=0.0)
        estimate = estimate_costs(report)
        assert estimate.current_cost_per_1k == 0
        assert estimate.breakeven_executions == 0


# ── Report Merging ───────────────────────────────────────────


class TestReportMerging:
    def _make_code_report(self):
        return CompilabilityReport(
            source_type="code",
            overall_score=0.65,
            total_decision_points=3,
            compilable_points=2,
            not_compilable_points=1,
            decision_points=[
                DecisionPoint(name="route_by_intent", description="Routes by intent",
                              compilability=Compilability.COMPILABLE, reason="finite routing", pattern="router"),
                DecisionPoint(name="refund_threshold", description="Amount check",
                              compilability=Compilability.COMPILABLE, reason="threshold", pattern="rules"),
                DecisionPoint(name="generate_response", description="Free-form gen",
                              compilability=Compilability.NOT_COMPILABLE, reason="open-ended", pattern="generator"),
            ],
            scenarios=[
                SuggestedScenario(name="support_routing", description="Route support tickets",
                                  states=["triage", "refund_review", "resolved"],
                                  actions=["auto_approve", "escalate"],
                                  observation_fields=["intent", "amount"],
                                  confidence=0.8, source="static_analysis"),
            ],
            warnings=["generate_response uses free-form LLM"],
            raw_analysis={"code_structure": {"files": 1}},
        )

    def _make_log_report(self):
        return CompilabilityReport(
            source_type="logs",
            overall_score=0.85,
            total_decision_points=2,
            compilable_points=2,
            decision_points=[
                DecisionPoint(name="route_by_intent", description="Intent routing from logs",
                              compilability=Compilability.COMPILABLE, reason="consistent in logs", pattern="router"),
                DecisionPoint(name="billing_lookup", description="Billing check",
                              compilability=Compilability.COMPILABLE, reason="deterministic", pattern="pipeline"),
            ],
            scenarios=[
                SuggestedScenario(name="support_routing", description="Route support tickets",
                                  states=["triage", "billing_review", "escalated", "resolved"],
                                  actions=["lookup_billing", "escalate", "close_ticket"],
                                  observation_fields=["intent", "customer_id"],
                                  confidence=0.88, source="log_analysis"),
            ],
            raw_analysis={"log_summary": {"entries": 100}},
        )

    def test_merge_source_type(self):
        merged = self._make_code_report().merge(self._make_log_report())
        assert merged.source_type == "both"

    def test_merge_deduplicates_decision_points(self):
        merged = self._make_code_report().merge(self._make_log_report())
        names = [dp.name for dp in merged.decision_points]
        # route_by_intent appears in both, should only appear once
        assert names.count("route_by_intent") == 1
        # All unique points present
        assert "refund_threshold" in names
        assert "generate_response" in names
        assert "billing_lookup" in names
        assert merged.total_decision_points == 4

    def test_merge_combines_scenarios(self):
        merged = self._make_code_report().merge(self._make_log_report())
        assert len(merged.scenarios) == 1
        sc = merged.scenarios[0]
        assert sc.name == "support_routing"
        assert sc.source == "code+logs"
        # States merged from both
        assert "triage" in sc.states
        assert "billing_review" in sc.states
        assert "refund_review" in sc.states
        # Actions merged
        assert "auto_approve" in sc.actions
        assert "lookup_billing" in sc.actions
        # Fields merged
        assert "intent" in sc.observation_fields
        assert "amount" in sc.observation_fields
        assert "customer_id" in sc.observation_fields

    def test_merge_boosts_confidence(self):
        merged = self._make_code_report().merge(self._make_log_report())
        sc = merged.scenarios[0]
        # Confidence should be boosted above the max of the two (0.88)
        assert sc.confidence > 0.88

    def test_merge_weighted_score(self):
        merged = self._make_code_report().merge(self._make_log_report())
        # Weighted average: (0.65*3 + 0.85*2) / (3+2) = 0.73
        assert 0.7 < merged.overall_score < 0.8

    def test_merge_combines_warnings(self):
        merged = self._make_code_report().merge(self._make_log_report())
        assert any("generate_response" in w for w in merged.warnings)

    def test_merge_combines_raw_analysis(self):
        merged = self._make_code_report().merge(self._make_log_report())
        assert "code_structure" in merged.raw_analysis
        assert "log_summary" in merged.raw_analysis


# ── Bridge (SuggestedScenario → DSC Scenario) ────────────────


class TestBridge:
    def test_scenario_from_suggestion(self):
        suggestion = SuggestedScenario(
            name="support_routing",
            description="Route customer support requests",
            states=["triage", "billing_review", "resolved"],
            actions=["lookup_billing", "escalate", "close_ticket"],
            observation_fields=["intent", "amount", "customer_id"],
            confidence=0.9,
            source="code+logs",
        )
        scenario = scenario_from_suggestion(suggestion, "my-project")

        assert scenario.project_id == "my-project"
        assert scenario.name == "support_routing"
        assert "Route customer support" in scenario.context
        assert "90%" in scenario.context
        assert len(scenario.observation_schema.fields) == 3
        assert "intent" in scenario.observation_schema.fields
        assert len(scenario.actions) == 3
        assert "lookup_billing" in scenario.actions
        assert scenario.metadata["confidence"] == 0.9

    def test_scenario_has_deterministic_id(self):
        suggestion = SuggestedScenario(
            name="test", description="test",
            states=[], actions=[], observation_fields=[],
            confidence=0.5,
        )
        s1 = scenario_from_suggestion(suggestion, "p1")
        s2 = scenario_from_suggestion(suggestion, "p1")
        assert s1.id == s2.id  # same name -> same id

    def test_scenarios_from_report_filters_by_confidence(self):
        report = CompilabilityReport(
            source_type="both",
            overall_score=0.7,
            scenarios=[
                SuggestedScenario(name="high", description="high conf",
                                  states=["a"], actions=["x"], observation_fields=["f"],
                                  confidence=0.9),
                SuggestedScenario(name="low", description="low conf",
                                  states=["a"], actions=["x"], observation_fields=["f"],
                                  confidence=0.3),
                SuggestedScenario(name="mid", description="mid conf",
                                  states=["a"], actions=["x"], observation_fields=["f"],
                                  confidence=0.6),
            ],
        )
        scenarios = scenarios_from_report(report, "proj", min_confidence=0.5)
        names = [s.name for s in scenarios]
        assert "high" in names
        assert "mid" in names
        assert "low" not in names

    def test_scenarios_from_report_empty(self):
        report = CompilabilityReport(source_type="code", overall_score=0.0)
        scenarios = scenarios_from_report(report, "proj")
        assert scenarios == []
