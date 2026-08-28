import { RunClient, RunOptions } from '../api/runClient';
import {
  ApplyResult,
  ProjectPickResponse,
  RunSnapshot,
  RunSummary,
  StoredEvent,
} from '../types/mission';

export const storedEvent = (sequence: number, name: string): StoredEvent => ({
  sequence,
  payload: {
    id: `run-a-${sequence}`, name, type: 'model', level: 'info',
    status_message: `${name} complete`, metadata: {}, agent: 'product',
    iteration: 0, at: sequence,
  },
});

export const approvedFixture = (events: StoredEvent[] = []): RunSnapshot => ({
  run_id: 'run-a', project_path: 'C:\\projects\\calculator',
  workspace_path: 'C:\\runs\\run-a', message: 'change it', phase: 'approved',
  events,
  report: {
    route_history: [], model_usage: [], changed_files: [{
      path: 'app.py', language: 'python', additions: 1, deletions: 1,
      lines: [{ type: 'del', text: 'old', oldNo: 1 },
              { type: 'add', text: 'new', newNo: 1 }],
    }],
    applied_diff: true, workspace_changed: true, source_applied: false,
    review: {
      status: 'APPROVED', score: 100,
      subscores: {
        requirements: 100, architecture: 100, security: 100,
        testing: 100, implementation: 100, rag_grounding: 100,
      },
      problems: [], reason: 'approved',
    },
    errors: [], rag_evidence: [], tool_results: [],
  },
  changed_paths: ['app.py'], apply_result: null,
  created_at: '2026-08-27T10:00:00-06:00',
  updated_at: '2026-08-27T10:01:00-06:00',
});

/** A complete, in-memory RunClient for tests. Reused by usePersistentRun tests (Task 6)
 *  and by the chat UI tests built on top of it (Task 7). */
export class FakeRunClient implements RunClient {
  requests: Array<{ projectPath: string; message: string; testSpec?: string; authorizeWrites: boolean }> = [];
  subscribeCalls = 0;
  getRunCalls = 0;
  private listener?: (value: StoredEvent | RunSnapshot) => void;
  private closeHandler?: () => void;

  constructor(public snapshot: RunSnapshot = approvedFixture()) {}

  async pickProject(): Promise<ProjectPickResponse> {
    return { status: 'selected', project: { path: 'C:\\projects\\calculator', name: 'calculator' } };
  }

  async selectProject(path: string): Promise<ProjectPickResponse> {
    return { status: 'selected', project: { path, name: path.split(/[\\/]/).filter(Boolean).at(-1) ?? path } };
  }

  async createRun(projectPath: string, message: string, options: RunOptions = {}): Promise<string> {
    this.requests.push({ projectPath, message, ...(options.testSpec ? { testSpec: options.testSpec } : {}), authorizeWrites: options.authorizeWrites === true });
    return `run-${this.requests.length}`;
  }

  async listRuns(): Promise<RunSummary[]> {
    return [];
  }

  async getRun(): Promise<RunSnapshot> {
    this.getRunCalls += 1;
    return this.snapshot;
  }

  async eventsAfter(_runId: string, after: number): Promise<StoredEvent[]> {
    return this.snapshot.events.filter((event) => event.sequence > after);
  }

  subscribe(
    _runId: string,
    _after: number,
    onEnvelope: (value: StoredEvent | RunSnapshot) => void,
    onClose?: () => void,
  ): () => void {
    this.subscribeCalls += 1;
    this.listener = onEnvelope;
    this.closeHandler = onClose;
    return () => {
      this.listener = undefined;
      this.closeHandler = undefined;
    };
  }

  async apply(): Promise<ApplyResult> {
    const result: ApplyResult = {
      status: 'applied', written_paths: ['app.py'], test_exit_code: 0,
      test_output: '1 passed', backup_path: 'backup', message: 'Applied',
    };
    // Mirror the real backend: a successful apply persists the new phase and
    // apply_result, which a post-apply refresh() must be able to observe.
    this.snapshot = { ...this.snapshot, phase: 'applied', apply_result: result, report: this.snapshot.report && { ...this.snapshot.report, source_applied: true } };
    return result;
  }

  async restore(): Promise<ApplyResult> {
    const result: ApplyResult = {
      status: 'restored', written_paths: ['app.py'], test_exit_code: null,
      test_output: '', backup_path: 'backup', message: 'Restored',
    };
    this.snapshot = { ...this.snapshot, phase: 'approved', apply_result: result };
    return result;
  }

  emit(value: StoredEvent | RunSnapshot): void {
    this.listener?.(value);
  }

  /** Simulates the transport closing (e.g. websocket onclose), triggering
   *  whatever reconnect/backoff behavior the consumer registered via onClose. */
  triggerClose(): void {
    this.closeHandler?.();
  }
}
