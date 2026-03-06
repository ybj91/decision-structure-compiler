"""Estimate cost savings from compiling agent decision logic."""

from __future__ import annotations

from dsc.analyzer.report import CompilabilityReport, CostEstimate


# Rough cost assumptions (per 1000 executions)
DEFAULT_AVG_TOKENS_PER_CALL = 2000  # input + output
DEFAULT_COST_PER_1K_TOKENS = 0.003  # ~Claude Sonnet pricing
DEFAULT_CALLS_PER_EXECUTION = 3     # average LLM calls per agent execution
DEFAULT_COMPILE_LLM_CALLS = 10      # LLM calls needed to compile one scenario


def estimate_costs(
    report: CompilabilityReport,
    tokens_per_call: int = DEFAULT_AVG_TOKENS_PER_CALL,
    cost_per_1k_tokens: float = DEFAULT_COST_PER_1K_TOKENS,
    calls_per_execution: int = DEFAULT_CALLS_PER_EXECUTION,
    compile_calls: int = DEFAULT_COMPILE_LLM_CALLS,
) -> CostEstimate:
    """Estimate cost savings based on compilability report.

    Returns a CostEstimate with current costs, compiled costs, and breakeven point.
    """
    if report.total_decision_points == 0:
        return CostEstimate(
            current_cost_per_1k=0,
            compiled_cost_per_1k=0,
            savings_percent=0,
            compile_cost=0,
            breakeven_executions=0,
        )

    cost_per_call = tokens_per_call * cost_per_1k_tokens / 1000
    current_cost_per_exec = cost_per_call * calls_per_execution
    current_cost_per_1k = current_cost_per_exec * 1000

    # After compilation, only non-compilable points still need LLM
    compilable_fraction = report.overall_score
    remaining_calls = calls_per_execution * (1 - compilable_fraction)
    compiled_cost_per_exec = cost_per_call * remaining_calls
    compiled_cost_per_1k = compiled_cost_per_exec * 1000

    # One-time compilation cost
    num_scenarios = max(len(report.scenarios), 1)
    compile_cost = cost_per_call * compile_calls * num_scenarios

    savings_per_exec = current_cost_per_exec - compiled_cost_per_exec
    if savings_per_exec > 0:
        breakeven = int(compile_cost / savings_per_exec) + 1
    else:
        breakeven = 0

    savings_pct = (1 - compiled_cost_per_1k / current_cost_per_1k) * 100 if current_cost_per_1k > 0 else 0

    return CostEstimate(
        current_cost_per_1k=round(current_cost_per_1k, 2),
        compiled_cost_per_1k=round(compiled_cost_per_1k, 2),
        savings_percent=round(savings_pct, 1),
        compile_cost=round(compile_cost, 4),
        breakeven_executions=breakeven,
    )
