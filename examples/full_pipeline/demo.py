"""Full Pipeline Demo -- the core DSC workflow.

This is the most important example. It shows what DSC is actually for:

  1. You define a scenario (what domain, what actions, what observations)
  2. The LLM SIMULATES execution traces for different test inputs
  3. The LLM EXTRACTS a decision graph from those traces
  4. The optimizer CLEANS UP the graph
  5. The compiler PRODUCES a runtime artifact
  6. The runtime EXECUTES deterministically -- no LLM needed

The user never writes a single trace by hand. The LLM does all the
reasoning at compile time, and the result is a fast, deterministic,
auditable state machine.

This demo mocks the LLM responses so you can run it without an API key.
In production, replace MockLLMClient with the real LLMClient and the
LLM generates all of this automatically.

Run:
    python examples/full_pipeline/demo.py
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from dsc.compiler.compiler import Compiler
from dsc.graph_extractor.extractor import GraphExtractor
from dsc.graph_optimizer.optimizer import GraphOptimizer
from dsc.models.scenario import (
    ActionDefinition,
    ObservationField,
    ObservationSchema,
    Scenario,
    ToolDefinition,
)
from dsc.models.project import Project
from dsc.runtime.engine import RuntimeConfig, RuntimeEngine
from dsc.storage.filesystem import FileSystemStorage
from dsc.trace_collector.collector import TraceCollector
from dsc.trace_collector.simulator import TraceSimulator

# =====================================================================
#  MOCK LLM RESPONSES
#
#  These are what Claude would actually return for each LLM call.
#  In production you use LLMClient() and the LLM generates these.
#  The format matches exactly what the Anthropic tool_use API returns.
# =====================================================================

# -- Trace simulation: "password reset" test case ---------------------
SIMULATED_TRACE_PASSWORD_RESET = {
    "initial_state": "triage",
    "steps": [
        {
            "state": "triage",
            "observation": {
                "issue_type": "account",
                "issue_description": "I can't log in, forgot my password",
                "customer_email": "alice@example.com",
                "severity": "low",
            },
            "decision": "This is a standard account access issue. The customer forgot their password. Route to account recovery flow.",
            "action": "initiate_password_reset",
            "action_params": {"email": "alice@example.com"},
            "tool_result": {"reset_link_sent": True, "expires_in_minutes": 30},
            "next_state": "awaiting_confirmation",
        },
        {
            "state": "awaiting_confirmation",
            "observation": {
                "reset_completed": True,
                "customer_satisfied": True,
            },
            "decision": "Customer confirmed they received the reset link and successfully changed their password. Issue resolved.",
            "action": "close_ticket",
            "action_params": {"resolution": "password_reset_successful"},
            "tool_result": None,
            "next_state": "resolved",
        },
    ],
}

# -- Trace simulation: "billing dispute" test case --------------------
SIMULATED_TRACE_BILLING = {
    "initial_state": "triage",
    "steps": [
        {
            "state": "triage",
            "observation": {
                "issue_type": "billing",
                "issue_description": "I was charged twice for my subscription",
                "customer_email": "bob@example.com",
                "severity": "medium",
            },
            "decision": "This is a billing dispute about a duplicate charge. Need to look up the customer's billing history to verify.",
            "action": "lookup_billing_history",
            "action_params": {"email": "bob@example.com", "period_days": 30},
            "tool_result": {
                "charges": [
                    {"date": "2024-01-01", "amount": 29.99, "description": "Monthly subscription"},
                    {"date": "2024-01-01", "amount": 29.99, "description": "Monthly subscription"},
                ],
                "duplicate_detected": True,
            },
            "next_state": "billing_review",
        },
        {
            "state": "billing_review",
            "observation": {
                "duplicate_confirmed": True,
                "refund_amount": 29.99,
            },
            "decision": "Duplicate charge confirmed by billing system. The amount is under $100 so auto-refund is authorized without manager approval.",
            "action": "process_refund",
            "action_params": {"amount": 29.99, "reason": "duplicate_charge"},
            "tool_result": {"refund_id": "ref-88721", "status": "processed"},
            "next_state": "refund_issued",
        },
        {
            "state": "refund_issued",
            "observation": {
                "customer_notified": True,
                "customer_satisfied": True,
            },
            "decision": "Refund processed and customer notified. They're satisfied. Close the ticket.",
            "action": "close_ticket",
            "action_params": {"resolution": "duplicate_charge_refunded"},
            "tool_result": None,
            "next_state": "resolved",
        },
    ],
}

# -- Trace simulation: "service outage" test case ---------------------
SIMULATED_TRACE_OUTAGE = {
    "initial_state": "triage",
    "steps": [
        {
            "state": "triage",
            "observation": {
                "issue_type": "technical",
                "issue_description": "Your entire service is down, nothing loads",
                "customer_email": "carol@example.com",
                "severity": "critical",
            },
            "decision": "This is a critical severity technical issue reporting a full service outage. Must escalate immediately to engineering -- this is beyond what support can fix.",
            "action": "check_system_status",
            "action_params": {},
            "tool_result": {"status": "degraded", "active_incidents": ["INC-2024-042"]},
            "next_state": "incident_detected",
        },
        {
            "state": "incident_detected",
            "observation": {
                "known_incident": True,
                "incident_id": "INC-2024-042",
                "estimated_resolution": "2 hours",
            },
            "decision": "There is a known active incident. Notify the customer about the ongoing incident and estimated resolution time rather than creating a duplicate ticket.",
            "action": "notify_known_incident",
            "action_params": {"incident_id": "INC-2024-042", "eta": "2 hours"},
            "tool_result": None,
            "next_state": "monitoring",
        },
        {
            "state": "monitoring",
            "observation": {
                "incident_resolved": True,
                "service_restored": True,
            },
            "decision": "The incident has been resolved and service is restored. Send resolution notification and close.",
            "action": "close_ticket",
            "action_params": {"resolution": "known_incident_resolved"},
            "tool_result": None,
            "next_state": "resolved",
        },
    ],
}

# -- Phase A: Raw transition extraction (one per trace) ---------------
PHASE_A_PASSWORD_RESET = {
    "transitions": [
        {
            "from_state": "triage",
            "condition_description": "customer has an account access issue like forgotten password",
            "action": "initiate_password_reset",
            "action_params": {"email": "alice@example.com"},
            "to_state": "awaiting_confirmation",
        },
        {
            "from_state": "awaiting_confirmation",
            "condition_description": "customer confirmed the password reset was successful",
            "action": "close_ticket",
            "action_params": {"resolution": "password_reset_successful"},
            "to_state": "resolved",
        },
    ]
}

PHASE_A_BILLING = {
    "transitions": [
        {
            "from_state": "triage",
            "condition_description": "customer reports a billing issue like duplicate charge",
            "action": "lookup_billing_history",
            "action_params": {},
            "to_state": "billing_review",
        },
        {
            "from_state": "billing_review",
            "condition_description": "duplicate charge is confirmed and amount is under $100",
            "action": "process_refund",
            "action_params": {},
            "to_state": "refund_issued",
        },
        {
            "from_state": "refund_issued",
            "condition_description": "refund processed and customer is satisfied",
            "action": "close_ticket",
            "action_params": {"resolution": "duplicate_charge_refunded"},
            "to_state": "resolved",
        },
    ]
}

PHASE_A_OUTAGE = {
    "transitions": [
        {
            "from_state": "triage",
            "condition_description": "customer reports a critical technical issue or service outage",
            "action": "check_system_status",
            "action_params": {},
            "to_state": "incident_detected",
        },
        {
            "from_state": "incident_detected",
            "condition_description": "there is a known active incident matching the customer's report",
            "action": "notify_known_incident",
            "action_params": {},
            "to_state": "monitoring",
        },
        {
            "from_state": "monitoring",
            "condition_description": "the incident has been resolved and service is restored",
            "action": "close_ticket",
            "action_params": {},
            "to_state": "resolved",
        },
    ]
}

# -- Phase B: State normalization across all 3 traces -----------------
PHASE_B_NORMALIZATION = {
    "canonical_states": [
        {
            "name": "triage",
            "description": "Initial state: classify the incoming support request",
            "original_names": ["triage"],
        },
        {
            "name": "awaiting_confirmation",
            "description": "Waiting for customer to confirm an action was successful",
            "original_names": ["awaiting_confirmation"],
        },
        {
            "name": "billing_review",
            "description": "Reviewing billing records to verify a charge dispute",
            "original_names": ["billing_review"],
        },
        {
            "name": "refund_issued",
            "description": "A refund has been processed, awaiting customer acknowledgment",
            "original_names": ["refund_issued"],
        },
        {
            "name": "incident_detected",
            "description": "A system incident has been identified matching the report",
            "original_names": ["incident_detected"],
        },
        {
            "name": "monitoring",
            "description": "Monitoring an active incident for resolution",
            "original_names": ["monitoring"],
        },
        {
            "name": "resolved",
            "description": "Ticket closed, issue resolved",
            "original_names": ["resolved"],
        },
    ]
}

# -- Phase C: Condition formalization into structured AST -------------
PHASE_C_FORMALIZATION = {
    "transitions": [
        # From triage: route by issue_type
        {
            "from_state": "triage",
            "condition": {
                "type": "field", "field": "issue_type", "operator": "eq", "value": "account",
            },
            "action": "initiate_password_reset",
            "action_params": {},
            "to_state": "awaiting_confirmation",
            "priority": 0,
        },
        {
            "from_state": "triage",
            "condition": {
                "type": "field", "field": "issue_type", "operator": "eq", "value": "billing",
            },
            "action": "lookup_billing_history",
            "action_params": {},
            "to_state": "billing_review",
            "priority": 1,
        },
        {
            "from_state": "triage",
            "condition": {
                "type": "group",
                "logic": "and",
                "conditions": [
                    {"type": "field", "field": "issue_type", "operator": "eq", "value": "technical"},
                    {"type": "field", "field": "severity", "operator": "eq", "value": "critical"},
                ],
            },
            "action": "check_system_status",
            "action_params": {},
            "to_state": "incident_detected",
            "priority": 2,
        },
        {
            "from_state": "triage",
            "condition": {"type": "always_true"},
            "action": "escalate_to_human",
            "action_params": {},
            "to_state": "resolved",
            "priority": 100,
        },
        # From awaiting_confirmation
        {
            "from_state": "awaiting_confirmation",
            "condition": {
                "type": "field", "field": "reset_completed", "operator": "eq", "value": True,
            },
            "action": "close_ticket",
            "action_params": {"resolution": "password_reset_successful"},
            "to_state": "resolved",
            "priority": 0,
        },
        {
            "from_state": "awaiting_confirmation",
            "condition": {"type": "always_true"},
            "action": "escalate_to_human",
            "action_params": {"reason": "reset_failed"},
            "to_state": "resolved",
            "priority": 100,
        },
        # From billing_review
        {
            "from_state": "billing_review",
            "condition": {
                "type": "group",
                "logic": "and",
                "conditions": [
                    {"type": "field", "field": "duplicate_confirmed", "operator": "eq", "value": True},
                    {"type": "field", "field": "refund_amount", "operator": "lte", "value": 100},
                ],
            },
            "action": "process_refund",
            "action_params": {},
            "to_state": "refund_issued",
            "priority": 0,
        },
        {
            "from_state": "billing_review",
            "condition": {
                "type": "group",
                "logic": "and",
                "conditions": [
                    {"type": "field", "field": "duplicate_confirmed", "operator": "eq", "value": True},
                    {"type": "field", "field": "refund_amount", "operator": "gt", "value": 100},
                ],
            },
            "action": "escalate_to_human",
            "action_params": {"reason": "high_value_refund"},
            "to_state": "resolved",
            "priority": 1,
        },
        {
            "from_state": "billing_review",
            "condition": {"type": "always_true"},
            "action": "escalate_to_human",
            "action_params": {"reason": "billing_unclear"},
            "to_state": "resolved",
            "priority": 100,
        },
        # From refund_issued
        {
            "from_state": "refund_issued",
            "condition": {
                "type": "field", "field": "customer_satisfied", "operator": "eq", "value": True,
            },
            "action": "close_ticket",
            "action_params": {"resolution": "refund_processed"},
            "to_state": "resolved",
            "priority": 0,
        },
        {
            "from_state": "refund_issued",
            "condition": {"type": "always_true"},
            "action": "escalate_to_human",
            "action_params": {"reason": "customer_unsatisfied_after_refund"},
            "to_state": "resolved",
            "priority": 100,
        },
        # From incident_detected
        {
            "from_state": "incident_detected",
            "condition": {
                "type": "field", "field": "known_incident", "operator": "eq", "value": True,
            },
            "action": "notify_known_incident",
            "action_params": {},
            "to_state": "monitoring",
            "priority": 0,
        },
        {
            "from_state": "incident_detected",
            "condition": {"type": "always_true"},
            "action": "escalate_to_human",
            "action_params": {"reason": "unknown_outage"},
            "to_state": "resolved",
            "priority": 100,
        },
        # From monitoring
        {
            "from_state": "monitoring",
            "condition": {
                "type": "field", "field": "incident_resolved", "operator": "eq", "value": True,
            },
            "action": "close_ticket",
            "action_params": {"resolution": "incident_resolved"},
            "to_state": "resolved",
            "priority": 0,
        },
        {
            "from_state": "monitoring",
            "condition": {"type": "always_true"},
            "action": "escalate_to_human",
            "action_params": {"reason": "incident_unresolved"},
            "to_state": "resolved",
            "priority": 100,
        },
    ],
    "terminal_states": ["resolved"],
}

# =====================================================================
#  BUILD A MOCK LLM CLIENT
#
#  This returns the pre-defined responses in the exact order that
#  the simulator + extractor call structured_request().
#
#  Call order for 3 traces:
#    1. simulate_trace  (password reset)
#    2. simulate_trace  (billing dispute)
#    3. simulate_trace  (service outage)
#    4. extract_transitions  (from trace 1)
#    5. extract_transitions  (from trace 2)
#    6. extract_transitions  (from trace 3)
#    7. normalize_states     (all states from all traces)
#    8. formalize_conditions (all transitions, normalized)
# =====================================================================

def build_mock_llm():
    mock = MagicMock()
    mock.structured_request.side_effect = [
        # 3x simulate_trace
        SIMULATED_TRACE_PASSWORD_RESET,
        SIMULATED_TRACE_BILLING,
        SIMULATED_TRACE_OUTAGE,
        # 3x extract_transitions (Phase A)
        PHASE_A_PASSWORD_RESET,
        PHASE_A_BILLING,
        PHASE_A_OUTAGE,
        # 1x normalize_states (Phase B)
        PHASE_B_NORMALIZATION,
        # 1x formalize_conditions (Phase C)
        PHASE_C_FORMALIZATION,
    ]
    return mock


# =====================================================================
#  THE ACTUAL PIPELINE
# =====================================================================

def main():
    print("=" * 70)
    print("  DECISION STRUCTURE COMPILER -- Full Pipeline Demo")
    print("  Tech Support Triage: from scenario definition to runtime")
    print("=" * 70)

    # ── Step 1: Define the scenario ──────────────────────────
    print("\n--- STEP 1: Define the scenario ---\n")

    scenario = Scenario(
        id="tech-support",
        project_id="demo",
        name="Tech Support Triage",
        context=(
            "Automated tech support system that triages incoming customer issues. "
            "Classifies issues by type (account, billing, technical), determines "
            "severity, and either resolves automatically or escalates to a human agent. "
            "Password resets and small refunds can be handled automatically. "
            "Critical outages should check system status first."
        ),
        observation_schema=ObservationSchema(fields={
            "issue_type": ObservationField(type="string", description="Category: account, billing, or technical"),
            "issue_description": ObservationField(type="string", description="Customer's description of the problem"),
            "customer_email": ObservationField(type="string", description="Customer email address"),
            "severity": ObservationField(type="string", description="low, medium, high, or critical"),
        }),
        actions={
            "initiate_password_reset": ActionDefinition(
                name="initiate_password_reset",
                description="Send a password reset link to the customer",
                tool="auth_service",
            ),
            "lookup_billing_history": ActionDefinition(
                name="lookup_billing_history",
                description="Look up recent charges for a customer",
                tool="billing_api",
            ),
            "process_refund": ActionDefinition(
                name="process_refund",
                description="Issue a refund to the customer",
                tool="billing_api",
            ),
            "check_system_status": ActionDefinition(
                name="check_system_status",
                description="Check for active incidents and system health",
                tool="status_page",
            ),
            "notify_known_incident": ActionDefinition(
                name="notify_known_incident",
                description="Inform customer about a known incident and ETA",
            ),
            "close_ticket": ActionDefinition(
                name="close_ticket",
                description="Close the support ticket with a resolution",
            ),
            "escalate_to_human": ActionDefinition(
                name="escalate_to_human",
                description="Transfer to a human support agent",
            ),
        },
        tools={
            "auth_service": ToolDefinition(
                name="auth_service",
                description="Authentication service for password resets",
            ),
            "billing_api": ToolDefinition(
                name="billing_api",
                description="Billing system for charge lookups and refunds",
            ),
            "status_page": ToolDefinition(
                name="status_page",
                description="System status and incident tracking",
            ),
        },
        constraints=[
            "Auto-refunds are only allowed for amounts under $100",
            "Critical severity issues must always check system status first",
            "If unsure about anything, escalate to a human agent",
        ],
    )

    print(f"  Scenario: {scenario.name}")
    print(f"  Actions:  {list(scenario.actions.keys())}")
    print(f"  Tools:    {list(scenario.tools.keys())}")
    print(f"  Context:  {scenario.context[:80]}...")

    # ── Step 2: LLM simulates traces ────────────────────────
    print("\n--- STEP 2: LLM simulates execution traces ---")
    print("  (In production, Claude generates these from the scenario + test inputs)\n")

    mock_llm = build_mock_llm()
    simulator = TraceSimulator(mock_llm)

    test_cases = [
        {"issue_type": "account", "issue_description": "I can't log in, forgot my password",
         "customer_email": "alice@example.com", "severity": "low"},
        {"issue_type": "billing", "issue_description": "I was charged twice for my subscription",
         "customer_email": "bob@example.com", "severity": "medium"},
        {"issue_type": "technical", "issue_description": "Your entire service is down, nothing loads",
         "customer_email": "carol@example.com", "severity": "critical"},
    ]

    traces = []
    for i, test_input in enumerate(test_cases, 1):
        trace = simulator.simulate(scenario, test_input)
        traces.append(trace)
        print(f"  Trace {i}: {test_input['issue_type']} ({test_input['severity']}) "
              f"-> {len(trace.steps)} steps")
        for step in trace.steps:
            print(f"    {step.state} -> [{step.action}] -> {step.next_state}")
            if step.decision:
                # Wrap long decision text
                words = step.decision.split()
                line = "      "
                for w in words:
                    if len(line) + len(w) > 76:
                        print(line)
                        line = "      " + w
                    else:
                        line += (" " if len(line) > 6 else "") + w
                if line.strip():
                    print(line)
        print()

    # ── Step 3: Store traces (validate chain consistency) ────
    print("--- STEP 3: Validate and store traces ---\n")

    data_dir = Path(tempfile.mkdtemp())
    storage = FileSystemStorage(data_dir)
    storage.save_project(Project(id="demo", name="Demo"))
    storage.save_scenario(scenario)

    collector = TraceCollector(storage)
    for trace in traces:
        collector.add_trace("demo", scenario.id, trace)
        print(f"  Stored trace {trace.id} ({len(trace.steps)} steps, chain validated)")

    # ── Step 4: LLM extracts the decision graph ─────────────
    print("\n--- STEP 4: LLM extracts decision graph (3-phase pipeline) ---\n")

    extractor = GraphExtractor(mock_llm)
    graph = extractor.extract(scenario, traces)

    print(f"  Phase A - Raw extraction:        {len(mock_llm.structured_request.call_args_list)} LLM calls total")
    print(f"  Phase B - State normalization:    {len(graph.states)} canonical states")
    print(f"  Phase C - Condition formalization: {len(graph.transitions)} structured transitions")
    print()
    print("  States discovered:")
    for name, state in graph.states.items():
        print(f"    [{name}] {state.description}")
    print()
    print("  Transitions formalized:")
    for t in graph.transitions:
        cond_str = _format_condition(t.condition)
        print(f"    {t.from_state} --[{cond_str}]--> {t.action} --> {t.to_state}  (pri={t.priority})")

    # ── Step 5: Optimize the graph ──────────────────────────
    print("\n--- STEP 5: Optimize the graph ---\n")

    optimizer = GraphOptimizer()
    optimized, report = optimizer.optimize(graph)
    optimized.version = 2

    print(f"  States:      {report.original_state_count} -> {report.final_state_count}")
    print(f"  Transitions: {report.original_transition_count} -> {report.final_transition_count}")
    print(f"  Removed:     {report.states_removed or '(none)'}")
    print(f"  Conflicts:   {len(report.conflicts)}")

    storage.save_graph("demo", optimized)

    # ── Step 6: Compile to artifact ─────────────────────────
    print("\n--- STEP 6: Compile to runtime artifact ---\n")

    compiler = Compiler(storage)
    artifact = compiler.compile("demo", scenario, optimized)

    print(f"  Artifact version: v{artifact.version}")
    print(f"  States: {len(artifact.data['graph']['states'])}")
    print(f"  Transitions: {len(artifact.data['graph']['transitions'])}")
    print(f"  Self-contained: yes (includes action + tool definitions)")

    # ── Step 7: Run deterministically ───────────────────────
    print("\n--- STEP 7: Execute at runtime (NO LLM CALLS) ---")

    actions_log = []

    def action_handler(action, params):
        actions_log.append(action)
        return {"status": "ok"}

    config = RuntimeConfig(action_handler=action_handler)

    # --- Test: Password reset ---
    _run_test(
        "PASSWORD RESET -- account issue, low severity",
        artifact, config, actions_log,
        [
            {"issue_type": "account", "severity": "low"},
            {"reset_completed": True, "customer_satisfied": True},
        ],
    )

    # --- Test: Billing refund (small amount) ---
    _run_test(
        "BILLING REFUND -- duplicate charge under $100",
        artifact, config, actions_log,
        [
            {"issue_type": "billing", "severity": "medium"},
            {"duplicate_confirmed": True, "refund_amount": 29.99},
            {"customer_satisfied": True},
        ],
    )

    # --- Test: Billing refund (large amount -> escalate) ---
    _run_test(
        "BILLING ESCALATION -- duplicate charge over $100",
        artifact, config, actions_log,
        [
            {"issue_type": "billing", "severity": "medium"},
            {"duplicate_confirmed": True, "refund_amount": 250.00},
        ],
    )

    # --- Test: Critical outage ---
    _run_test(
        "CRITICAL OUTAGE -- known incident",
        artifact, config, actions_log,
        [
            {"issue_type": "technical", "severity": "critical"},
            {"known_incident": True, "incident_id": "INC-2024-042"},
            {"incident_resolved": True, "service_restored": True},
        ],
    )

    # --- Test: Unknown issue type -> fallback ---
    _run_test(
        "UNKNOWN ISSUE -- falls through to human escalation",
        artifact, config, actions_log,
        [
            {"issue_type": "shipping", "severity": "low"},
        ],
    )

    # ── Summary ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"""
  The LLM was used 8 times at COMPILE TIME to:
    - Simulate 3 execution traces from test inputs
    - Extract raw transitions from each trace
    - Normalize states across all traces
    - Formalize conditions into structured expressions

  The result is a compiled artifact with:
    - {len(artifact.data['graph']['states'])} states
    - {len(artifact.data['graph']['transitions'])} transitions
    - Full condition AST (evaluated deterministically)

  At RUNTIME, we ran 5 different test scenarios with:
    - 0 LLM calls
    - Deterministic, auditable execution
    - Sub-millisecond per step
    - Every decision traceable to a specific condition
""")


def _run_test(name, artifact, config, actions_log, observations):
    print(f"\n  {'~' * 60}")
    print(f"  {name}")
    print(f"  {'~' * 60}")

    engine = RuntimeEngine.from_artifact(artifact, config)
    engine.start()
    actions_log.clear()

    for obs in observations:
        if engine.is_terminal:
            break
        result = engine.step(obs)
        print(f"    [{result.from_state}] + {_compact(obs)}")
        print(f"      -> {result.action} -> [{result.to_state}]")

    status = "RESOLVED" if engine.is_terminal else "IN PROGRESS"
    print(f"    Result: {status} in {engine.step_count} steps | "
          f"Actions: {actions_log}")


def _compact(d):
    """Format a dict compactly for display."""
    parts = []
    for k, v in d.items():
        if isinstance(v, str) and len(v) > 20:
            v = v[:17] + "..."
        parts.append(f"{k}={v}")
    return "{" + ", ".join(parts) + "}"


def _format_condition(cond):
    """Format a condition for human-readable display."""
    from dsc.models.conditions import AlwaysTrue, ConditionGroup, FieldCondition

    if isinstance(cond, AlwaysTrue):
        return "default"
    if isinstance(cond, FieldCondition):
        return f"{cond.field} {cond.operator.value} {cond.value!r}"
    if isinstance(cond, ConditionGroup):
        inner = f" {cond.logic.value} ".join(_format_condition(c) for c in cond.conditions)
        return f"({inner})"
    return "?"


if __name__ == "__main__":
    main()
