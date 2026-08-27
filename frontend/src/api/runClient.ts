import { FinalReport, LaunchConfig, RunEvent } from '../types/mission';

interface LocationLike {
  protocol: string;
  host: string;
}

const AGENTS = new Set([
  'product', 'architecture', 'developer', 'security', 'testing', 'reviewer', 'human_review'
]);
const EVENT_TYPES = new Set(['rag', 'tool', 'model', 'error']);
const EVENT_LEVELS = new Set(['info', 'warn', 'error']);

const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export function isRunEvent(value: unknown): value is RunEvent {
  if (!object(value)) return false;
  return typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    typeof value.status_message === 'string' &&
    EVENT_TYPES.has(String(value.type)) &&
    EVENT_LEVELS.has(String(value.level)) &&
    object(value.metadata) &&
    AGENTS.has(String(value.agent)) &&
    typeof value.iteration === 'number' &&
    typeof value.at === 'number';
}

export function isFinalReport(value: unknown): value is FinalReport {
  if (!object(value) || !object(value.review)) return false;
  return Array.isArray(value.route_history) &&
    Array.isArray(value.model_usage) &&
    Array.isArray(value.changed_files) &&
    typeof value.applied_diff === 'boolean' &&
    typeof value.review.status === 'string' &&
    Array.isArray(value.errors) &&
    Array.isArray(value.rag_evidence) &&
    Array.isArray(value.tool_results);
}

export async function launchRun(config: LaunchConfig, signal?: AbortSignal): Promise<string> {
  const response = await fetch('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
    signal
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  const payload = await response.json() as { run_id?: unknown };
  if (typeof payload.run_id !== 'string') throw new Error('Backend did not return run_id');
  return payload.run_id;
}

export function websocketUrl(
  runId: string,
  location: LocationLike = window.location
): string {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${location.host}/ws/runs/${encodeURIComponent(runId)}`;
}
