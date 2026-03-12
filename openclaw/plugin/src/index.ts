/**
 * DSC ContextEngine Plugin for OpenClaw
 *
 * Intercepts incoming messages and checks if any compiled DSC artifact
 * can handle the request deterministically. If yes, returns the action
 * immediately (<1ms, 0 tokens). If no, falls through to the LLM.
 *
 * This is the "hybrid agent" pattern: compiled decisions run instantly,
 * only genuinely novel inputs use the LLM.
 */

import { evaluate, Transition, CompiledArtifact } from "./evaluator";
import { loadArtifacts, watchArtifacts, LoadedArtifact } from "./loader";

interface PluginConfig {
  artifactsDir: string;
  enabled: boolean;
  fallbackToLLM: boolean;
  logCompiledHits: boolean;
}

interface MatchResult {
  matched: boolean;
  scenarioName?: string;
  fromState?: string;
  action?: string;
  actionParams?: Record<string, unknown>;
  toState?: string;
}

interface PluginStats {
  compiledHits: number;
  llmFallbacks: number;
  totalRequests: number;
  savedTokens: number;
  startedAt: Date;
}

const DEFAULT_CONFIG: PluginConfig = {
  artifactsDir: "./compiled",
  enabled: true,
  fallbackToLLM: true,
  logCompiledHits: true,
};

// Average tokens per LLM call (used for savings estimation)
const AVG_TOKENS_PER_CALL = 2000;

let config: PluginConfig = { ...DEFAULT_CONFIG };
let artifacts: LoadedArtifact[] = [];
let stats: PluginStats = {
  compiledHits: 0,
  llmFallbacks: 0,
  totalRequests: 0,
  savedTokens: 0,
  startedAt: new Date(),
};

/**
 * Initialize the DSC ContextEngine plugin.
 */
export function init(pluginConfig: Partial<PluginConfig> = {}): void {
  config = { ...DEFAULT_CONFIG, ...pluginConfig };
  artifacts = loadArtifacts(config.artifactsDir);

  // Watch for artifact changes (hot reload)
  watchArtifacts(config.artifactsDir, (updated) => {
    artifacts = updated;
  });

  if (artifacts.length > 0) {
    const totalStates = artifacts.reduce(
      (sum, a) => sum + Object.keys(a.artifact.graph.states).length,
      0
    );
    const totalTransitions = artifacts.reduce(
      (sum, a) => sum + a.artifact.graph.transitions.length,
      0
    );
    console.log(
      `[DSC] Loaded ${artifacts.length} compiled artifact(s): ${totalStates} states, ${totalTransitions} transitions`
    );
  } else {
    console.log(`[DSC] No compiled artifacts found in ${config.artifactsDir}`);
  }
}

/**
 * Try to match an observation against all compiled artifacts.
 * Returns the first matching transition (by priority).
 */
export function tryCompiledPath(
  observation: Record<string, unknown>,
  currentState?: string
): MatchResult {
  if (!config.enabled || artifacts.length === 0) {
    return { matched: false };
  }

  for (const { artifact } of artifacts) {
    const state = currentState || artifact.graph.initial_state;

    // Get transitions from the current state, sorted by priority
    const transitions = artifact.graph.transitions
      .filter((t: Transition) => t.from_state === state)
      .sort((a: Transition, b: Transition) => (a.priority || 0) - (b.priority || 0));

    for (const transition of transitions) {
      if (evaluate(transition.condition, observation)) {
        return {
          matched: true,
          scenarioName: artifact.scenario_name,
          fromState: state,
          action: transition.action,
          actionParams: transition.action_params || {},
          toState: transition.to_state,
        };
      }
    }
  }

  return { matched: false };
}

/**
 * ContextEngine lifecycle hook: beforeModelCall
 *
 * Called by OpenClaw before sending a request to the LLM.
 * If a compiled path matches, we short-circuit and return directly.
 */
export function beforeModelCall(context: {
  message: string;
  observation?: Record<string, unknown>;
  state?: string;
}): { intercepted: boolean; response?: string; metadata?: Record<string, unknown> } {
  stats.totalRequests++;

  if (!config.enabled) {
    stats.llmFallbacks++;
    return { intercepted: false };
  }

  // Build observation from context
  const observation = context.observation || parseObservation(context.message);

  const result = tryCompiledPath(observation, context.state);

  if (result.matched) {
    stats.compiledHits++;
    stats.savedTokens += AVG_TOKENS_PER_CALL;

    if (config.logCompiledHits) {
      console.log(
        `[DSC] Compiled hit: ${result.scenarioName} | ${result.fromState} -> [${result.action}] -> ${result.toState}`
      );
    }

    return {
      intercepted: true,
      response: undefined, // Action handler will generate the response
      metadata: {
        dsc: true,
        scenario: result.scenarioName,
        action: result.action,
        actionParams: result.actionParams,
        fromState: result.fromState,
        toState: result.toState,
        tokensUsed: 0,
      },
    };
  }

  stats.llmFallbacks++;
  return { intercepted: false };
}

/**
 * Best-effort extraction of structured observation from a plain text message.
 * In practice, OpenClaw skills/tools provide structured data — this is the fallback.
 */
function parseObservation(message: string): Record<string, unknown> {
  const lower = message.toLowerCase();
  const obs: Record<string, unknown> = { raw_message: message };

  // Intent detection heuristics
  const intentPatterns: Record<string, string[]> = {
    refund: ["refund", "return", "money back", "charge back"],
    billing: ["bill", "invoice", "charge", "payment", "subscription"],
    account: ["password", "login", "sign in", "locked out", "access"],
    technical: ["error", "bug", "broken", "not working", "crash", "down"],
    complaint: ["complain", "unhappy", "terrible", "worst", "angry"],
  };

  for (const [intent, keywords] of Object.entries(intentPatterns)) {
    if (keywords.some((kw) => lower.includes(kw))) {
      obs.intent = intent;
      break;
    }
  }

  // Extract amounts
  const amountMatch = message.match(/\$(\d+(?:\.\d{2})?)/);
  if (amountMatch) {
    obs.amount = parseFloat(amountMatch[1]);
  }

  // Extract order/ticket numbers
  const orderMatch = message.match(/#(\d+)/);
  if (orderMatch) {
    obs.order_id = orderMatch[1];
  }

  return obs;
}

/**
 * Get plugin statistics.
 */
export function getStats(): PluginStats & { hitRate: string; estimatedSavings: string } {
  const hitRate =
    stats.totalRequests > 0
      ? ((stats.compiledHits / stats.totalRequests) * 100).toFixed(1) + "%"
      : "0%";

  const costPerToken = 0.000003; // ~$3/1M tokens
  const saved = (stats.savedTokens * costPerToken).toFixed(4);

  return {
    ...stats,
    hitRate,
    estimatedSavings: `$${saved}`,
  };
}

/**
 * Get loaded artifact summaries.
 */
export function getArtifactSummaries(): Array<{
  name: string;
  states: number;
  transitions: number;
  initialState: string;
}> {
  return artifacts.map(({ artifact }) => ({
    name: artifact.scenario_name,
    states: Object.keys(artifact.graph.states).length,
    transitions: artifact.graph.transitions.length,
    initialState: artifact.graph.initial_state,
  }));
}
