import { useEffect, useRef, useState } from 'react';
import { launchRun, isFinalReport, isRunEvent, websocketUrl } from '../api/runClient';
import { AgentId, Beat, FinalReport, LaunchConfig, Provider, RunEvent, RunStatus } from '../types/mission';

export interface ActiveEdge {
  key: number;
  from: AgentId;
  to: AgentId;
  kind: 'forward' | 'reject' | 'branch';
  duration: number;
}

interface Options {
  config: LaunchConfig;
  onComplete: (report: FinalReport, runId: string) => void;
  /** Kept for source compatibility; real runs never consume prototype beats or speed. */
  beats?: Beat[];
  speed?: number;
}

interface RunState {
  runId: string;
  activeAgent: AgentId | null;
  caption: string;
  iteration: number;
  status: RunStatus;
  events: RunEvent[];
  providers: Record<AgentId, Provider | null>;
  fallbacks: Record<string, string>;
  activeEdge: ActiveEdge | null;
  visitedEdges: string[];
  elapsed: number;
  finished: boolean;
}

const EMPTY_PROVIDERS: Record<AgentId, Provider | null> = {
  product: null, architecture: null, developer: null, security: null,
  testing: null, reviewer: null, human_review: null
};

const edgeKind = (from: AgentId, to: AgentId): ActiveEdge['kind'] => {
  if (from === 'reviewer' && (to === 'architecture' || to === 'developer')) return 'reject';
  if ((from === 'security' && to === 'human_review') || from === 'human_review') return 'branch';
  return 'forward';
};

const providerFrom = (event: RunEvent): Provider | null => {
  const value = String(event.metadata.provider ?? event.model ?? '').toLowerCase();
  if (value.includes('ollama') || value.includes('qwen')) return 'local';
  if (value.includes('gemini') || value.includes('groq') || value.includes('cloud')) return 'cloud';
  return null;
};

export function useRunSimulation({ config, onComplete }: Options): RunState {
  const [runId, setRunId] = useState('starting…');
  const [activeAgent, setActiveAgent] = useState<AgentId | null>(null);
  const [caption, setCaption] = useState('starting isolated workflow…');
  const [iteration, setIteration] = useState(0);
  const [status, setStatus] = useState<RunStatus>('RUNNING');
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [providers, setProviders] = useState(EMPTY_PROVIDERS);
  const [fallbacks, setFallbacks] = useState<Record<string, string>>({});
  const [activeEdge, setActiveEdge] = useState<ActiveEdge | null>(null);
  const [visitedEdges, setVisitedEdges] = useState<string[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [finished, setFinished] = useState(false);
  const startedAt = useRef(Date.now());
  const previousAgent = useRef<AgentId | null>(null);
  const sequence = useRef(0);
  const completeRef = useRef(onComplete);
  completeRef.current = onComplete;

  useEffect(() => {
    const timer = window.setInterval(() => setElapsed(Date.now() - startedAt.current), 100);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    let socket: WebSocket | null = null;
    let disposed = false;

    const connect = async () => {
      try {
        const id = await launchRun(config, abort.signal);
        if (disposed) return;
        setRunId(id);
        socket = new WebSocket(websocketUrl(id));
        socket.onmessage = (message) => {
          const payload: unknown = JSON.parse(String(message.data));
          if (isRunEvent(payload)) {
            const prior = previousAgent.current;
            if (prior && prior !== payload.agent) {
              const edgeId = `${prior}-${payload.agent}`;
              setActiveEdge({
                key: sequence.current++, from: prior, to: payload.agent,
                kind: edgeKind(prior, payload.agent), duration: 700
              });
              setVisitedEdges((current) => current.includes(edgeId) ? current : [...current, edgeId]);
            }
            previousAgent.current = payload.agent;
            setActiveAgent(payload.agent);
            setCaption(payload.status_message);
            setIteration(payload.iteration);
            setEvents((current) => [...current, payload].slice(-40));
            const provider = providerFrom(payload);
            if (provider) setProviders((current) => ({ ...current, [payload.agent]: provider }));
            if (String(payload.metadata.fallback_used) === 'true') {
              setFallbacks((current) => ({
                ...current,
                [payload.agent]: String(payload.metadata.fallback_reason || 'backend fallback')
              }));
            }
            return;
          }
          if (isFinalReport(payload)) {
            setStatus(payload.review.status);
            setFinished(true);
            completeRef.current(payload, id);
          }
        };
        socket.onerror = () => setCaption('live transport connection failed');
      } catch (error) {
        if (!disposed && !abort.signal.aborted) {
          setCaption(error instanceof Error ? error.message : 'run could not be started');
        }
      }
    };
    void connect();
    return () => {
      disposed = true;
      abort.abort();
      socket?.close();
    };
  }, [config]);

  return {
    runId, activeAgent, caption, iteration, status, events, providers, fallbacks,
    activeEdge, visitedEdges, elapsed, finished
  };
}
