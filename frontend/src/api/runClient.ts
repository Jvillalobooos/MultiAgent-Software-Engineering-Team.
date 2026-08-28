import {
  ApplyResult,
  FinalReport,
  ProjectPickResponse,
  RunPhase,
  RunSnapshot,
  RunSummary,
  StoredEvent,
} from '../types/mission';

interface LocationLike {
  protocol: string;
  host: string;
}

const RUN_PHASES = new Set<string>([
  'queued', 'preparing', 'running', 'review_required', 'approved',
  'failed', 'applying', 'applied', 'apply_failed',
]);
const APPLY_STATUSES = new Set(['applied', 'apply_failed', 'restored', 'conflict']);
const PICK_STATUSES = new Set(['selected', 'cancelled']);

const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const hasValidRunOptions = (value: Record<string, unknown>): boolean =>
  (value.test_spec === undefined || value.test_spec === null || typeof value.test_spec === 'string') &&
  (value.authorize_writes === undefined || typeof value.authorize_writes === 'boolean') &&
  (value.trace_id === undefined || value.trace_id === null || typeof value.trace_id === 'string');

/* ---------- Transport guards ---------- */

export function isFinalReport(value: unknown): value is FinalReport {
  if (!object(value) || !object(value.review)) return false;
  return Array.isArray(value.route_history) &&
    Array.isArray(value.model_usage) &&
    Array.isArray(value.changed_files) &&
    typeof value.applied_diff === 'boolean' &&
    typeof value.workspace_changed === 'boolean' &&
    typeof value.source_applied === 'boolean' &&
    typeof value.review.status === 'string' &&
    Array.isArray(value.errors) &&
    Array.isArray(value.rag_evidence) &&
    Array.isArray(value.tool_results);
}

export function websocketUrl(
  runId: string,
  location: LocationLike = window.location
): string {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${location.host}/ws/runs/${encodeURIComponent(runId)}`;
}

/* ---------- Persistent run contract guards (Task 6) ---------- */

export function isRunPhase(value: unknown): value is RunPhase {
  return typeof value === 'string' && RUN_PHASES.has(value);
}

export function isStoredEvent(value: unknown): value is StoredEvent {
  if (!object(value)) return false;
  return typeof value.sequence === 'number' &&
    Number.isInteger(value.sequence) &&
    value.sequence >= 1 &&
    object(value.payload);
}

export function isProjectPickResponse(value: unknown): value is ProjectPickResponse {
  if (!object(value)) return false;
  if (!PICK_STATUSES.has(String(value.status))) return false;
  if (value.status === 'cancelled') return value.project === null;
  return object(value.project) &&
    typeof value.project.path === 'string' &&
    typeof value.project.name === 'string';
}

export function isApplyResult(value: unknown): value is ApplyResult {
  if (!object(value)) return false;
  if (!APPLY_STATUSES.has(String(value.status))) return false;
  return Array.isArray(value.written_paths) &&
    value.written_paths.every((path) => typeof path === 'string') &&
    (value.test_exit_code === null || typeof value.test_exit_code === 'number') &&
    typeof value.test_output === 'string' &&
    (value.backup_path === null || typeof value.backup_path === 'string') &&
    typeof value.message === 'string';
}

export function isRunSummary(value: unknown): value is RunSummary {
  if (!object(value) || !hasValidRunOptions(value)) return false;
  return typeof value.run_id === 'string' &&
    typeof value.project_path === 'string' &&
    typeof value.message === 'string' &&
    isRunPhase(value.phase) &&
    typeof value.created_at === 'string' &&
    typeof value.updated_at === 'string';
}

export function isRunSnapshot(value: unknown): value is RunSnapshot {
  if (!object(value) || !hasValidRunOptions(value)) return false;
  const structurallyValid = typeof value.run_id === 'string' &&
    typeof value.project_path === 'string' &&
    typeof value.workspace_path === 'string' &&
    typeof value.message === 'string' &&
    isRunPhase(value.phase) &&
    Array.isArray(value.events) &&
    value.events.every(isStoredEvent) &&
    (value.report === null || isFinalReport(value.report)) &&
    Array.isArray(value.changed_paths) &&
    value.changed_paths.every((path) => typeof path === 'string') &&
    (value.apply_result === null || isApplyResult(value.apply_result)) &&
    typeof value.created_at === 'string' &&
    typeof value.updated_at === 'string';
  if (!structurallyValid) return false;
  // A run cannot reach `approved` without a persisted terminal report: the frontend
  // must never render approval as inferred, only as data the backend actually stored.
  if (value.phase === 'approved' && value.report === null) return false;
  return true;
}

/* ---------- Typed API errors ---------- */

export class RunApiError extends Error {
  readonly code: string;
  readonly recoverable: boolean;
  readonly details?: unknown;

  constructor(code: string, message: string, recoverable: boolean, details?: unknown) {
    super(message);
    this.name = 'RunApiError';
    this.code = code;
    this.recoverable = recoverable;
    this.details = details;
  }
}

export function isRunApiError(value: unknown): value is RunApiError {
  return value instanceof RunApiError;
}

async function toRunApiError(response: Response): Promise<RunApiError> {
  // Recoverability is a fact the backend owns via detail.recoverable -- it is never
  // inferred from the HTTP status code here. The status-code heuristic below is only
  // a fallback for the rare case a response lacks the structured error shape.
  const fallbackRecoverable = response.status >= 500;
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  const detail = body?.detail;
  if (object(detail) && typeof detail.code === 'string' && typeof detail.message === 'string') {
    const recoverable = typeof detail.recoverable === 'boolean' ? detail.recoverable : fallbackRecoverable;
    return new RunApiError(detail.code, detail.message, recoverable, detail);
  }
  if (typeof detail === 'string') {
    return new RunApiError(`HTTP_${response.status}`, detail, fallbackRecoverable, detail);
  }
  return new RunApiError(
    `HTTP_${response.status}`,
    `HTTP ${response.status}`,
    fallbackRecoverable,
    detail ?? null,
  );
}

/* ---------- RunClient ---------- */

export interface RunOptions {
  testSpec?: string;
  authorizeWrites?: boolean;
}

export interface RunClient {
  pickProject(signal?: AbortSignal): Promise<ProjectPickResponse>;
  selectProject(path: string, signal?: AbortSignal): Promise<ProjectPickResponse>;
  createRun(projectPath: string, message: string, options?: RunOptions, signal?: AbortSignal): Promise<string>;
  listRuns(signal?: AbortSignal): Promise<RunSummary[]>;
  getRun(runId: string, signal?: AbortSignal): Promise<RunSnapshot>;
  eventsAfter(runId: string, after: number, signal?: AbortSignal): Promise<StoredEvent[]>;
  subscribe(
    runId: string,
    after: number,
    onEnvelope: (value: StoredEvent | RunSnapshot) => void,
    onClose: () => void,
  ): () => void;
  apply(runId: string, projectPath: string): Promise<ApplyResult>;
  restore(runId: string): Promise<ApplyResult>;
}

export class HttpRunClient implements RunClient {
  async pickProject(signal?: AbortSignal): Promise<ProjectPickResponse> {
    const response = await fetch('/api/projects/pick', { method: 'POST', signal });
    if (!response.ok) throw await toRunApiError(response);
    const payload: unknown = await response.json();
    if (!isProjectPickResponse(payload)) {
      throw new RunApiError('INVALID_RESPONSE', 'Backend returned a malformed project pick response', false, payload);
    }
    return payload;
  }

  async selectProject(path: string, signal?: AbortSignal): Promise<ProjectPickResponse> {
    const response = await fetch('/api/projects/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
      signal,
    });
    if (!response.ok) throw await toRunApiError(response);
    const payload: unknown = await response.json();
    if (!isProjectPickResponse(payload) || payload.status !== 'selected') {
      throw new RunApiError('INVALID_RESPONSE', 'Backend returned a malformed project selection response', false, payload);
    }
    return payload;
  }

  async createRun(projectPath: string, message: string, options: RunOptions = {}, signal?: AbortSignal): Promise<string> {
    const testSpec = options.testSpec?.trim();
    const response = await fetch('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        projectPath,
        message,
        ...(testSpec ? { testSpec } : {}),
        authorizeWrites: options.authorizeWrites === true,
      }),
      signal,
    });
    if (!response.ok) throw await toRunApiError(response);
    const payload = await response.json() as { run_id?: unknown };
    if (typeof payload.run_id !== 'string') {
      throw new RunApiError('INVALID_RESPONSE', 'Backend did not return run_id', false, payload);
    }
    return payload.run_id;
  }

  async listRuns(signal?: AbortSignal): Promise<RunSummary[]> {
    const response = await fetch('/api/runs', { signal });
    if (!response.ok) throw await toRunApiError(response);
    const payload: unknown = await response.json();
    if (!Array.isArray(payload) || !payload.every(isRunSummary)) {
      throw new RunApiError('INVALID_RESPONSE', 'Backend returned malformed run summaries', false, payload);
    }
    return payload;
  }

  async getRun(runId: string, signal?: AbortSignal): Promise<RunSnapshot> {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { signal });
    if (!response.ok) throw await toRunApiError(response);
    const payload: unknown = await response.json();
    if (!isRunSnapshot(payload)) {
      throw new RunApiError('INVALID_RESPONSE', 'Backend returned a malformed run snapshot', false, payload);
    }
    return payload;
  }

  async eventsAfter(runId: string, after: number, signal?: AbortSignal): Promise<StoredEvent[]> {
    const response = await fetch(
      `/api/runs/${encodeURIComponent(runId)}/events?after=${encodeURIComponent(String(after))}`,
      { signal },
    );
    if (!response.ok) throw await toRunApiError(response);
    const payload: unknown = await response.json();
    if (!Array.isArray(payload) || !payload.every(isStoredEvent)) {
      throw new RunApiError('INVALID_RESPONSE', 'Backend returned malformed events', false, payload);
    }
    return payload;
  }

  subscribe(
    runId: string,
    after: number,
    onEnvelope: (value: StoredEvent | RunSnapshot) => void,
    onClose: () => void,
  ): () => void {
    const socket = new WebSocket(`${websocketUrl(runId)}?after=${encodeURIComponent(String(after))}`);
    socket.onmessage = (message) => {
      let payload: unknown;
      try {
        payload = JSON.parse(String(message.data));
      } catch {
        return;
      }
      if (!object(payload)) return;
      if (payload.kind === 'event') {
        const { sequence, payload: eventPayload } = payload as { sequence?: unknown; payload?: unknown };
        const candidate = { sequence, payload: eventPayload };
        if (isStoredEvent(candidate)) onEnvelope(candidate);
        return;
      }
      if (payload.kind === 'snapshot' && isRunSnapshot(payload.snapshot)) {
        onEnvelope(payload.snapshot);
      }
    };
    socket.onclose = () => onClose();
    socket.onerror = () => socket.close();
    return () => {
      socket.onmessage = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.close();
    };
  }

  async apply(runId: string, projectPath: string): Promise<ApplyResult> {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projectPath, confirmed: true }),
    });
    if (!response.ok) throw await toRunApiError(response);
    const payload: unknown = await response.json();
    if (!isApplyResult(payload)) {
      throw new RunApiError('INVALID_RESPONSE', 'Backend returned a malformed apply result', false, payload);
    }
    return payload;
  }

  async restore(runId: string): Promise<ApplyResult> {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/restore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed: true }),
    });
    if (!response.ok) throw await toRunApiError(response);
    const payload: unknown = await response.json();
    if (!isApplyResult(payload)) {
      throw new RunApiError('INVALID_RESPONSE', 'Backend returned a malformed restore result', false, payload);
    }
    return payload;
  }
}

/** Default real-transport client the app uses; tests inject FakeRunClient instead. */
export const runClient: RunClient = new HttpRunClient();
