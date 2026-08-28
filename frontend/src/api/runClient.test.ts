import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  HttpRunClient,
  isApplyResult,
  isProjectPickResponse,
  isRunApiError,
  isRunSnapshot,
  isRunSummary,
  isStoredEvent,
  RunApiError,
} from './runClient';
import { approvedFixture, storedEvent } from '../test/FakeRunClient';
import { RunPhase, RunSnapshot } from '../types/mission';

const ALL_PHASES: RunPhase[] = [
  'queued', 'preparing', 'running', 'review_required', 'approved',
  'failed', 'applying', 'applied', 'apply_failed',
];

const baseSnapshot = (phase: RunPhase, report: RunSnapshot['report'] = null): RunSnapshot => ({
  run_id: 'run-a',
  project_path: 'C:\\projects\\calculator',
  workspace_path: 'C:\\runs\\run-a',
  message: 'change it',
  phase,
  events: [],
  report,
  changed_paths: [],
  apply_result: null,
  created_at: '2026-08-27T10:00:00-06:00',
  updated_at: '2026-08-27T10:01:00-06:00',
});

describe('run contract guards', () => {
  it('rejects malformed optional execution permissions rather than treating them as truthy', () => {
    expect(isRunSnapshot({ ...baseSnapshot('running'), authorize_writes: 'false' })).toBe(false);
    expect(isRunSnapshot({ ...baseSnapshot('running'), test_spec: 42 })).toBe(false);
    expect(isRunSnapshot({ ...baseSnapshot('running'), authorize_writes: false, test_spec: null })).toBe(true);
  });
  it('accepts a valid snapshot for every RunPhase', () => {
    for (const phase of ALL_PHASES) {
      const report = phase === 'approved' ? approvedFixture().report : null;
      expect(isRunSnapshot(baseSnapshot(phase, report))).toBe(true);
    }
  });

  it('rejects an unknown phase value', () => {
    expect(isRunSnapshot(baseSnapshot('bogus' as RunPhase))).toBe(false);
  });

  it('rejects an approved snapshot without a persisted report', () => {
    expect(isRunSnapshot({
      run_id: 'run-a', project_path: 'C:\\work', workspace_path: 'C:\\runs\\run-a',
      message: 'change it', phase: 'approved', source_hashes: {}, events: [],
      report: null, changed_paths: [], apply_result: null,
      created_at: '2026-08-27T10:00:00-06:00', updated_at: '2026-08-27T10:01:00-06:00',
    })).toBe(false);
  });

  it('rejects an approved snapshot whose report is missing workspace_changed or source_applied', () => {
    const fullReport = approvedFixture().report!;

    const { workspace_changed, ...withoutWorkspaceChanged } = fullReport;
    expect(isRunSnapshot(baseSnapshot('approved', withoutWorkspaceChanged as RunSnapshot['report']))).toBe(false);

    const { source_applied, ...withoutSourceApplied } = fullReport;
    expect(isRunSnapshot(baseSnapshot('approved', withoutSourceApplied as RunSnapshot['report']))).toBe(false);

    expect(isRunSnapshot(baseSnapshot('approved', { ...fullReport, workspace_changed: 'yes' } as unknown as RunSnapshot['report']))).toBe(false);
    expect(isRunSnapshot(baseSnapshot('approved', { ...fullReport, source_applied: 1 } as unknown as RunSnapshot['report']))).toBe(false);
  });

  it('rejects a snapshot missing required fields', () => {
    expect(isRunSnapshot({ run_id: 'run-a' })).toBe(false);
    expect(isRunSnapshot(null)).toBe(false);
    expect(isRunSnapshot('run-a')).toBe(false);
  });

  it('validates stored events by sequence and payload shape', () => {
    expect(isStoredEvent(storedEvent(1, 'Product'))).toBe(true);
    expect(isStoredEvent({ sequence: 0, payload: {} })).toBe(false);
    expect(isStoredEvent({ sequence: 1, payload: null })).toBe(false);
    expect(isStoredEvent({ payload: {} })).toBe(false);
  });

  it('validates the selected and cancelled project picker responses', () => {
    expect(isProjectPickResponse({
      status: 'selected', project: { path: 'C:\\projects\\calculator', name: 'calculator' },
    })).toBe(true);
    expect(isProjectPickResponse({ status: 'cancelled', project: null })).toBe(true);
    expect(isProjectPickResponse({ status: 'selected', project: null })).toBe(false);
    expect(isProjectPickResponse({ status: 'unknown', project: null })).toBe(false);
  });

  it('validates apply results across every terminal status', () => {
    expect(isApplyResult({
      status: 'applied', written_paths: ['app.py'], test_exit_code: 0,
      test_output: '1 passed', backup_path: 'backup', message: 'Applied',
    })).toBe(true);
    expect(isApplyResult({
      status: 'conflict', written_paths: [], test_exit_code: null,
      test_output: '', backup_path: null, message: 'Project changed since approval',
    })).toBe(true);
    expect(isApplyResult({
      status: 'restored', written_paths: ['app.py'], test_exit_code: null,
      test_output: '', backup_path: 'backup', message: 'Restored',
    })).toBe(true);
    expect(isApplyResult({
      status: 'apply_failed', written_paths: [], test_exit_code: 1,
      test_output: 'FAILED', backup_path: 'backup', message: 'Apply failed',
    })).toBe(true);
    expect(isApplyResult({ status: 'bogus' })).toBe(false);
    expect(isApplyResult({ status: 'applied', written_paths: 'app.py' })).toBe(false);
  });

  it('validates run summaries', () => {
    expect(isRunSummary({
      run_id: 'run-a', project_path: 'C:\\projects\\calculator', message: 'change it',
      phase: 'queued', created_at: '2026-08-27T10:00:00-06:00', updated_at: '2026-08-27T10:00:00-06:00',
    })).toBe(true);
    expect(isRunSummary({ run_id: 'run-a' })).toBe(false);
  });

  it('recognizes a recoverable RunApiError instance', () => {
    const error = new RunApiError('NETWORK_ERROR', 'fetch failed', true, undefined);
    expect(isRunApiError(error)).toBe(true);
    expect(error.recoverable).toBe(true);
    expect(isRunApiError(new Error('plain'))).toBe(false);
  });
});

function stubFetchOnce(status: number, body: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false,
    status,
    json: () => Promise.resolve(body),
  }));
}

describe('HttpRunClient project selection and execution modes', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends a typed path for server validation without rewriting platform separators', async () => {
    const project = { path: 'C:\\Proyectos\\Cálculo', name: 'Cálculo' };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'selected', project }) });
    vi.stubGlobal('fetch', fetchMock);

    expect(await new HttpRunClient().selectProject(project.path)).toEqual({ status: 'selected', project });
    expect(fetchMock).toHaveBeenCalledWith('/api/projects/select', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ path: project.path }),
    }));
  });

  it('explicitly disables writes when execution options are omitted', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ run_id: 'dry-run' }) });
    vi.stubGlobal('fetch', fetchMock);

    expect(await new HttpRunClient().createRun('/tmp/demo', 'Fix median')).toBe('dry-run');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      projectPath: '/tmp/demo', message: 'Fix median', authorizeWrites: false,
    });
  });

  it('sends an independent test specification and explicit write authorization', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ run_id: 'write-run' }) });
    vi.stubGlobal('fetch', fetchMock);
    await new HttpRunClient().createRun('/tmp/demo', 'Fix median', {
      testSpec: 'Test mediana([7,8,9,10]) == 8.5', authorizeWrites: true,
    });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      projectPath: '/tmp/demo', message: 'Fix median',
      testSpec: 'Test mediana([7,8,9,10]) == 8.5', authorizeWrites: true,
    });
  });

  it('rejects a malformed manual-selection response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'selected', project: null }) }));
    await expect(new HttpRunClient().selectProject('/tmp/demo')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
});

describe('HttpRunClient error envelopes', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('uses the backend recoverable flag on a 4xx response instead of the status heuristic', async () => {
    stubFetchOnce(409, {
      detail: { code: 'RUN_NOT_APPROVED', message: 'not approved', recoverable: true },
    });
    const client = new HttpRunClient();

    await expect(client.apply('run-a', 'C:\\proj')).rejects.toMatchObject({
      code: 'RUN_NOT_APPROVED',
      recoverable: true,
    });
  });

  it('uses the backend recoverable flag on a 5xx response instead of the status heuristic', async () => {
    stubFetchOnce(500, {
      detail: { code: 'WORKFLOW_ERROR', message: 'internal', recoverable: false },
    });
    const client = new HttpRunClient();

    await expect(client.getRun('run-a')).rejects.toMatchObject({
      code: 'WORKFLOW_ERROR',
      recoverable: false,
    });
  });

  it('falls back to a status-code heuristic only when the response lacks the structured shape', async () => {
    stubFetchOnce(500, {});
    const client = new HttpRunClient();

    await expect(client.getRun('run-a')).rejects.toMatchObject({
      code: 'HTTP_500',
      recoverable: true,
    });
  });
});
