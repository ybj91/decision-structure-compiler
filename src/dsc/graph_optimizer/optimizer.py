"""Decision graph optimization — state merging, pruning, and conflict detection.

Uses networkx for graph analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from dsc.models.conditions import AlwaysTrue
from dsc.models.graph import DecisionGraph, StateDefinition, Transition
from dsc.runtime.evaluator import evaluate


@dataclass
class OptimizationReport:
    """Statistics from the optimization process."""

    original_state_count: int = 0
    original_transition_count: int = 0
    final_state_count: int = 0
    final_transition_count: int = 0
    states_removed: list[str] = field(default_factory=list)
    duplicate_transitions_merged: int = 0
    conflicts: list[dict] = field(default_factory=list)


class GraphOptimizer:
    """Optimizes a DecisionGraph by merging states, pruning unreachable nodes,
    and detecting conflicts."""

    def optimize(self, graph: DecisionGraph) -> tuple[DecisionGraph, OptimizationReport]:
        """Run the full optimization pipeline.

        Returns (optimized_graph, report).
        """
        report = OptimizationReport(
            original_state_count=len(graph.states),
            original_transition_count=len(graph.transitions),
        )

        states = dict(graph.states)
        transitions = list(graph.transitions)
        terminal_states = list(graph.terminal_states)

        # Step 1: Remove unreachable states
        transitions, states, removed = self._remove_unreachable(
            graph.initial_state, states, transitions
        )
        report.states_removed = removed
        terminal_states = [s for s in terminal_states if s in states]

        # Step 2: Merge duplicate transitions
        transitions, merged_count = self._merge_duplicate_transitions(transitions)
        report.duplicate_transitions_merged = merged_count

        # Step 3: Merge equivalent states
        transitions, states, terminal_states = self._merge_equivalent_states(
            transitions, states, terminal_states
        )

        # Step 4: Detect conflicts
        report.conflicts = self._detect_conflicts(transitions)

        report.final_state_count = len(states)
        report.final_transition_count = len(transitions)

        optimized = DecisionGraph(
            id=graph.id,
            scenario_id=graph.scenario_id,
            version=graph.version,
            states=states,
            transitions=transitions,
            initial_state=graph.initial_state,
            terminal_states=terminal_states,
            metadata={
                **graph.metadata,
                "optimization": {
                    "states_removed": report.states_removed,
                    "duplicates_merged": report.duplicate_transitions_merged,
                    "conflict_count": len(report.conflicts),
                },
            },
        )

        return optimized, report

    def _remove_unreachable(
        self,
        initial_state: str,
        states: dict[str, StateDefinition],
        transitions: list[Transition],
    ) -> tuple[list[Transition], dict[str, StateDefinition], list[str]]:
        """BFS from initial state; remove anything unreachable."""
        g = nx.DiGraph()
        for s in states:
            g.add_node(s)
        for t in transitions:
            g.add_edge(t.from_state, t.to_state)

        if initial_state not in g:
            return transitions, states, []

        reachable = set(nx.descendants(g, initial_state)) | {initial_state}
        removed = [s for s in states if s not in reachable]

        new_states = {s: d for s, d in states.items() if s in reachable}
        new_transitions = [
            t for t in transitions
            if t.from_state in reachable and t.to_state in reachable
        ]

        return new_transitions, new_states, removed

    def _merge_duplicate_transitions(
        self, transitions: list[Transition]
    ) -> tuple[list[Transition], int]:
        """Merge transitions with identical from_state, to_state, action, and condition."""
        seen: dict[str, Transition] = {}
        merged_count = 0

        for t in transitions:
            key = f"{t.from_state}|{t.to_state}|{t.action}|{t.condition.model_dump_json()}"
            if key in seen:
                # Merge source traces
                existing = seen[key]
                combined_traces = list(set(existing.source_traces + t.source_traces))
                seen[key] = Transition(
                    from_state=existing.from_state,
                    condition=existing.condition,
                    action=existing.action,
                    action_params=existing.action_params,
                    to_state=existing.to_state,
                    priority=min(existing.priority, t.priority),
                    source_traces=combined_traces,
                )
                merged_count += 1
            else:
                seen[key] = t

        return list(seen.values()), merged_count

    def _merge_equivalent_states(
        self,
        transitions: list[Transition],
        states: dict[str, StateDefinition],
        terminal_states: list[str],
    ) -> tuple[list[Transition], dict[str, StateDefinition], list[str]]:
        """Merge states with identical outgoing transition sets.

        Two states are equivalent if they have the same set of
        (condition, action, to_state) on their outgoing transitions.
        """
        # Build outgoing signature per state
        outgoing: dict[str, list[str]] = {s: [] for s in states}
        for t in transitions:
            sig = f"{t.condition.model_dump_json()}|{t.action}|{t.to_state}"
            if t.from_state in outgoing:
                outgoing[t.from_state].append(sig)

        # Normalize signatures
        sig_to_states: dict[str, list[str]] = {}
        for state, sigs in outgoing.items():
            key = "||".join(sorted(sigs))
            sig_to_states.setdefault(key, []).append(state)

        # Build merge mapping (only merge groups with >1 state)
        merge_map: dict[str, str] = {}
        for group in sig_to_states.values():
            if len(group) > 1:
                canonical = sorted(group)[0]
                for s in group:
                    if s != canonical:
                        merge_map[s] = canonical

        if not merge_map:
            return transitions, states, terminal_states

        # Apply merge
        def remap(s: str) -> str:
            return merge_map.get(s, s)

        new_transitions = [
            Transition(
                from_state=remap(t.from_state),
                condition=t.condition,
                action=t.action,
                action_params=t.action_params,
                to_state=remap(t.to_state),
                priority=t.priority,
                source_traces=t.source_traces,
            )
            for t in transitions
        ]

        new_states = {
            name: defn for name, defn in states.items()
            if name not in merge_map
        }

        new_terminal = list(set(remap(s) for s in terminal_states))

        # Deduplicate transitions after remapping
        new_transitions, _ = self._merge_duplicate_transitions(new_transitions)

        return new_transitions, new_states, new_terminal

    def _detect_conflicts(self, transitions: list[Transition]) -> list[dict]:
        """Detect transitions from the same state with overlapping conditions
        but different actions or targets.

        Returns a list of conflict descriptions.
        """
        conflicts = []
        # Group by from_state
        by_state: dict[str, list[Transition]] = {}
        for t in transitions:
            by_state.setdefault(t.from_state, []).append(t)

        for state, state_transitions in by_state.items():
            # Check pairs for potential conflicts
            for i, a in enumerate(state_transitions):
                for b in state_transitions[i + 1:]:
                    if a.action == b.action and a.to_state == b.to_state:
                        continue  # Same outcome, not a real conflict

                    # Both AlwaysTrue → definitely conflicts
                    if isinstance(a.condition, AlwaysTrue) and isinstance(b.condition, AlwaysTrue):
                        conflicts.append({
                            "state": state,
                            "transition_a": f"{a.action} → {a.to_state}",
                            "transition_b": f"{b.action} → {b.to_state}",
                            "reason": "Multiple default transitions with different outcomes",
                        })

                    # Same condition but different outcomes
                    elif a.condition.model_dump_json() == b.condition.model_dump_json():
                        conflicts.append({
                            "state": state,
                            "transition_a": f"{a.action} → {a.to_state}",
                            "transition_b": f"{b.action} → {b.to_state}",
                            "reason": "Identical conditions with different outcomes",
                        })

        return conflicts
