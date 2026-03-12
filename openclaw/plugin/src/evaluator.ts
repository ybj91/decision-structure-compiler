/**
 * DSC Condition Evaluator — TypeScript port of the Python runtime evaluator.
 *
 * Pure function: evaluate(condition, observation) -> boolean
 * Handles nested field paths, type mismatches, and all 10 operators.
 */

export interface FieldCondition {
  type: "field";
  field: string;
  operator: string;
  value: unknown;
}

export interface ConditionGroup {
  type: "group";
  logic: "and" | "or" | "not";
  conditions: Condition[];
}

export interface AlwaysTrue {
  type: "always_true";
}

export type Condition = FieldCondition | ConditionGroup | AlwaysTrue;

export interface Transition {
  from_state: string;
  condition: Condition;
  action: string;
  action_params: Record<string, unknown>;
  to_state: string;
  priority: number;
}

export interface CompiledArtifact {
  version: number;
  scenario_id: string;
  scenario_name: string;
  graph: {
    states: Record<string, { description: string; is_terminal: boolean }>;
    transitions: Transition[];
    initial_state: string;
  };
}

/**
 * Resolve a dot-path field from an observation object.
 * e.g., "customer.tier" from { customer: { tier: "vip" } } -> "vip"
 */
function resolveField(path: string, observation: Record<string, unknown>): unknown {
  const parts = path.split(".");
  let current: unknown = observation;

  for (const part of parts) {
    if (current === null || current === undefined || typeof current !== "object") {
      return undefined;
    }
    current = (current as Record<string, unknown>)[part];
  }

  return current;
}

/**
 * Evaluate a single condition against an observation.
 */
export function evaluate(condition: Condition, observation: Record<string, unknown>): boolean {
  switch (condition.type) {
    case "always_true":
      return true;

    case "field":
      return evaluateField(condition, observation);

    case "group":
      return evaluateGroup(condition, observation);

    default:
      return false;
  }
}

function evaluateField(condition: FieldCondition, observation: Record<string, unknown>): boolean {
  const fieldValue = resolveField(condition.field, observation);

  if (fieldValue === undefined) {
    return false;
  }

  const expected = condition.value;

  switch (condition.operator) {
    case "eq":
      return fieldValue === expected;
    case "ne":
      return fieldValue !== expected;
    case "gt":
      return typeof fieldValue === "number" && typeof expected === "number" && fieldValue > expected;
    case "lt":
      return typeof fieldValue === "number" && typeof expected === "number" && fieldValue < expected;
    case "gte":
      return typeof fieldValue === "number" && typeof expected === "number" && fieldValue >= expected;
    case "lte":
      return typeof fieldValue === "number" && typeof expected === "number" && fieldValue <= expected;
    case "in":
      return Array.isArray(expected) && expected.includes(fieldValue);
    case "not_in":
      return Array.isArray(expected) && !expected.includes(fieldValue);
    case "contains":
      return typeof fieldValue === "string" && typeof expected === "string" && fieldValue.includes(expected);
    case "matches":
      if (typeof fieldValue === "string" && typeof expected === "string") {
        try {
          return new RegExp(expected).test(fieldValue);
        } catch {
          return false;
        }
      }
      return false;
    default:
      return false;
  }
}

function evaluateGroup(condition: ConditionGroup, observation: Record<string, unknown>): boolean {
  switch (condition.logic) {
    case "and":
      return condition.conditions.every((c) => evaluate(c, observation));
    case "or":
      return condition.conditions.some((c) => evaluate(c, observation));
    case "not":
      return condition.conditions.length > 0 && !evaluate(condition.conditions[0], observation);
    default:
      return false;
  }
}
