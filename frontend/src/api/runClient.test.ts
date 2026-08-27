import { describe, expect, it } from 'vitest';
import { isFinalReport, isRunEvent, websocketUrl } from './runClient';

describe('run transport contract', () => {
  it('distinguishes the terminal report from an ordered run event', () => {
    expect(isRunEvent({
      id: 'run-1-1', name: 'Product model', type: 'model', level: 'info',
      status_message: 'completed', metadata: {}, agent: 'product', iteration: 0, at: 1
    })).toBe(true);
    expect(isFinalReport({
      route_history: [], model_usage: [], changed_files: [], applied_diff: false,
      review: { status: 'APPROVED', score: 90, subscores: {}, problems: [], reason: 'ok' },
      errors: [], rag_evidence: [], tool_results: []
    })).toBe(true);
  });

  it('uses the page protocol and the backend run identifier for websocket connections', () => {
    expect(websocketUrl('run-a', { protocol: 'https:', host: 'nova.test' })).toBe(
      'wss://nova.test/ws/runs/run-a'
    );
  });

  it('rejects transport envelopes and incomplete objects', () => {
    expect(isRunEvent({ type: 'event', payload: {} })).toBe(false);
    expect(isFinalReport({ review: {}, errors: [] })).toBe(false);
  });
});
