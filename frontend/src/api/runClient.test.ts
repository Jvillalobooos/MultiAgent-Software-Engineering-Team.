import { describe, expect, it } from 'vitest';
import {
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
