import { useMemo } from 'react';
import { AgentId, Provider, RunEvent } from '../types/mission';
import { EDGE_MAP } from '../data/agents';
import { ActiveEdge } from '../components/mission/AgentGraph';

/** One hop the run actually took, in order. Drives the route trace. */
export interface RouteHop {
  agent: AgentId;
  iteration: number;
  /** The edge walked to reach this agent, when the graph has one for the pair. */
  edgeId: string | null;
  kind: 'forward' | 'reject' | 'branch' | null;
}

export interface RunGraphState {
  activeAgent: AgentId | null;
  visitedAgents: AgentId[];
  activeEdge: ActiveEdge | null;
  visitedEdges: string[];
  providers: Record<AgentId, Provider | null>;
  /** Agent → the model that took over after the requested one failed. */
  fallbacks: Record<string, string>;
  route: RouteHop[];
  caption: string;
  iteration: number;
}

const EMPTY_PROVIDERS = (): Record<AgentId, Provider | null> => ({
  product: null,
  architecture: null,
  developer: null,
  security: null,
  testing: null,
  reviewer: null,
  human_review: null,
});

/** Recorded provider names, mapped onto the two the graph renders. `ollama` is the
 *  only local runtime; every other provider the backend reports is a cloud API. */
const toProvider = (recorded: string): Provider =>
  recorded.toLowerCase() === 'ollama' ? 'local' : 'cloud';

const asText = (value: unknown): string | null =>
  typeof value === 'string' && value.length > 0 ? value : null;

/** Derives everything the agent graph animates from the run's own recorded events.
 *
 *  Nothing here is simulated. Each transition between consecutive events is a hop the
 *  workflow really took, each provider badge is the provider the backend really used,
 *  and a fallback badge appears only when the model that answered differs from the
 *  model that was requested. Transitions with no edge in the static graph still count
 *  as route hops — they just have no path to animate along. */
export function useRunGraph(events: RunEvent[]): RunGraphState {
  return useMemo(() => {
    const providers = EMPTY_PROVIDERS();
    const fallbacks: Record<string, string> = {};
    const visitedAgents: AgentId[] = [];
    const visitedEdges: string[] = [];
    const route: RouteHop[] = [];

    let activeEdge: ActiveEdge | null = null;
    let previousAgent: AgentId | null = null;

    events.forEach((event, index) => {
      const agent = event.agent;

      if (agent !== previousAgent) {
        const edgeId = previousAgent ? `${previousAgent}-${agent}` : null;
        const edge = edgeId ? EDGE_MAP[edgeId] : undefined;
        if (edge) {
          if (!visitedEdges.includes(edge.id)) visitedEdges.push(edge.id);
          activeEdge = {
            // Keying on the event index restarts the particle stream on every hop,
            // including a repeat of an edge already walked in an earlier iteration.
            key: index,
            from: edge.from,
            to: edge.to,
            kind: edge.kind,
            duration: edge.kind === 'reject' ? 1600 : 1200,
          };
        } else if (previousAgent) {
          activeEdge = null;
        }
        route.push({
          agent,
          iteration: event.iteration,
          edgeId: edge ? edge.id : null,
          kind: edge ? edge.kind : null,
        });
        if (!visitedAgents.includes(agent)) visitedAgents.push(agent);
        previousAgent = agent;
      }

      if (event.type === 'model') {
        const recorded = asText(event.metadata.provider);
        if (recorded) providers[agent] = toProvider(recorded);
        // A fallback is a fact the backend records: the model that answered is not
        // the model that was asked for.
        const requested = asText(event.metadata.requested_model);
        const actual = asText(event.metadata.actual_model) ?? asText(event.model);
        if (requested && actual && requested !== actual) fallbacks[agent] = actual;
      }
    });

    const last = events[events.length - 1];
    return {
      activeAgent: last ? last.agent : null,
      visitedAgents,
      activeEdge,
      visitedEdges,
      providers,
      fallbacks,
      route,
      caption: last ? last.status_message : '',
      iteration: events.reduce((highest, event) => Math.max(highest, event.iteration), 0),
    };
  }, [events]);
}
