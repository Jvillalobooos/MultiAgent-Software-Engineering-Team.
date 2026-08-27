import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { usePersistentRun } from './usePersistentRun';
import { approvedFixture, storedEvent } from '../test/FakeRunClient';
import { FakeRunClient } from '../test/FakeRunClient';
import { RunSnapshot, StoredEvent } from '../types/mission';

describe('usePersistentRun', () => {
  it('loads a snapshot and ignores replayed event sequences', async () => {
    const client = new FakeRunClient(approvedFixture([storedEvent(1, 'Product'), storedEvent(2, 'Developer')]));
    const { result } = renderHook(() => usePersistentRun('run-a', client));

    await waitFor(() => expect(result.current.events.map((e) => e.sequence)).toEqual([1, 2]));

    act(() => client.emit(storedEvent(2, 'duplicate')));
    act(() => client.emit(storedEvent(3, 'Testing')));

    expect(result.current.events.map((e) => e.sequence)).toEqual([1, 2, 3]);
  });

  it('exposes the loaded snapshot phase and report', async () => {
    const client = new FakeRunClient(approvedFixture([]));
    const { result } = renderHook(() => usePersistentRun('run-a', client));

    await waitFor(() => expect(result.current.snapshot).not.toBeNull());

    expect(result.current.snapshot?.phase).toBe('approved');
    expect(result.current.snapshot?.report).not.toBeNull();
  });

  it('merges a terminal snapshot envelope pushed over the subscription', async () => {
    const client = new FakeRunClient(approvedFixture([storedEvent(1, 'Product')]));
    client.snapshot = { ...client.snapshot, phase: 'running', report: null };
    const { result } = renderHook(() => usePersistentRun('run-a', client));

    await waitFor(() => expect(result.current.snapshot?.phase).toBe('running'));

    const terminal = approvedFixture([storedEvent(1, 'Product')]);
    act(() => client.emit(terminal));

    await waitFor(() => expect(result.current.snapshot?.phase).toBe('approved'));
  });

  it('unsubscribes on unmount', async () => {
    const client = new FakeRunClient(approvedFixture([]));
    const unsubscribe = vi.fn();
    const originalSubscribe = client.subscribe.bind(client);
    client.subscribe = (
      runId: string,
      after: number,
      onEnvelope: (value: StoredEvent | RunSnapshot) => void,
      onClose: () => void,
    ) => {
      const dispose = originalSubscribe(runId, after, onEnvelope, onClose);
      return () => {
        unsubscribe();
        dispose();
      };
    };
    const { result, unmount } = renderHook(() => usePersistentRun('run-a', client));
    await waitFor(() => expect(result.current.snapshot).not.toBeNull());

    unmount();

    expect(unsubscribe).toHaveBeenCalled();
  });

  it('reconnects with bounded backoff when the connection closes during an active phase', async () => {
    vi.useFakeTimers();
    try {
      const client = new FakeRunClient(approvedFixture([]));
      client.snapshot = { ...client.snapshot, phase: 'running', report: null };
      const { result } = renderHook(() => usePersistentRun('run-a', client));

      await vi.waitFor(() => expect(result.current.snapshot?.phase).toBe('running'));
      expect(client.getRunCalls).toBe(1);
      expect(client.subscribeCalls).toBe(1);

      act(() => client.triggerClose());

      // Nothing happens until the backoff delay elapses.
      expect(client.getRunCalls).toBe(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(250);
      });

      expect(client.getRunCalls).toBe(2);
      expect(client.subscribeCalls).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not reconnect when the connection closes in a terminal phase', async () => {
    vi.useFakeTimers();
    try {
      const client = new FakeRunClient(approvedFixture([]));
      const { result } = renderHook(() => usePersistentRun('run-a', client));

      await vi.waitFor(() => expect(result.current.snapshot?.phase).toBe('approved'));
      expect(client.getRunCalls).toBe(1);
      expect(client.subscribeCalls).toBe(1);

      act(() => client.triggerClose());

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });

      expect(client.getRunCalls).toBe(1);
      expect(client.subscribeCalls).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not fire a pending reconnect after unmount', async () => {
    vi.useFakeTimers();
    try {
      const client = new FakeRunClient(approvedFixture([]));
      client.snapshot = { ...client.snapshot, phase: 'running', report: null };
      const { result, unmount } = renderHook(() => usePersistentRun('run-a', client));

      await vi.waitFor(() => expect(result.current.snapshot?.phase).toBe('running'));

      act(() => client.triggerClose());
      unmount();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });

      expect(client.getRunCalls).toBe(1);
      expect(client.subscribeCalls).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('refresh() re-fetches the run and merges the newly persisted snapshot', async () => {
    const client = new FakeRunClient(approvedFixture([]));
    const { result } = renderHook(() => usePersistentRun('run-a', client));

    await waitFor(() => expect(result.current.snapshot?.phase).toBe('approved'));
    const callsBeforeRefresh = client.getRunCalls;

    client.snapshot = {
      ...client.snapshot,
      phase: 'applied',
      apply_result: {
        status: 'applied', written_paths: ['app.py'], test_exit_code: 0,
        test_output: '1 passed', backup_path: 'backup', message: 'applied successfully',
      },
    };

    await act(async () => {
      await result.current.refresh();
    });

    expect(client.getRunCalls).toBe(callsBeforeRefresh + 1);
    expect(result.current.snapshot?.phase).toBe('applied');
    expect(result.current.snapshot?.apply_result?.status).toBe('applied');
  });
});
