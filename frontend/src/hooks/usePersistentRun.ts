import { useCallback, useEffect, useRef, useState } from 'react';
import { RunClient } from '../api/runClient';
import { RunSnapshot, StoredEvent } from '../types/mission';

const _ACTIVE_PHASES = new Set(['queued', 'preparing', 'running', 'applying']);
const BACKOFF_STEPS_MS = [250, 500, 1000, 2000];

export interface PersistentRunState {
  snapshot: RunSnapshot | null;
  events: StoredEvent[];
  error: unknown;
  /** Force a fresh client.getRun() load and merge it into state. Used after an
   *  action (apply/restore) whose result is only durably reflected in a re-fetched
   *  snapshot -- the websocket may already be closed (phase left the active set) so
   *  nothing else will push this update to the consumer. */
  refresh: () => Promise<void>;
}

/** Snapshot-first, deduplicating subscription to one durable run.
 *  Loads the persisted snapshot before subscribing, connects at the highest
 *  already-observed sequence, merges only strictly-greater sequences (so a
 *  reconnect replay can never duplicate an event), and reconnects with bounded
 *  backoff while the run has not reached a terminal phase. */
export function usePersistentRun(runId: string, client: RunClient): PersistentRunState {
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [events, setEvents] = useState<StoredEvent[]>([]);
  const [error, setError] = useState<unknown>(null);

  const cursorRef = useRef(0);
  const attemptRef = useRef(0);
  const disposedRef = useRef(false);
  const unsubscribeRef = useRef<(() => void) | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshRef = useRef<() => Promise<void>>(() => Promise.resolve());

  useEffect(() => {
    disposedRef.current = false;
    cursorRef.current = 0;
    attemptRef.current = 0;
    setSnapshot(null);
    setEvents([]);
    setError(null);

    const clearTimer = () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const teardownSubscription = () => {
      unsubscribeRef.current?.();
      unsubscribeRef.current = null;
    };

    const mergeEvent = (event: StoredEvent) => {
      if (event.sequence <= cursorRef.current) return;
      cursorRef.current = event.sequence;
      setEvents((current) => [...current, event]);
    };

    const phaseRef = { current: 'queued' as RunSnapshot['phase'] };

    const applySnapshot = (next: RunSnapshot) => {
      phaseRef.current = next.phase;
      setSnapshot(next);
      for (const event of next.events) mergeEvent(event);
    };

    refreshRef.current = async () => {
      if (disposedRef.current) return;
      try {
        const loaded = await client.getRun(runId);
        if (disposedRef.current) return;
        applySnapshot(loaded);
      } catch (caught) {
        if (disposedRef.current) return;
        setError(caught);
      }
    };

    const scheduleReconnect = () => {
      if (disposedRef.current) return;
      const index = Math.min(attemptRef.current, BACKOFF_STEPS_MS.length - 1);
      const delay = BACKOFF_STEPS_MS[index];
      attemptRef.current += 1;
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        void connect();
      }, delay);
    };

    const connect = async () => {
      if (disposedRef.current) return;
      try {
        const loaded = await client.getRun(runId);
        if (disposedRef.current) return;
        applySnapshot(loaded);

        teardownSubscription();
        unsubscribeRef.current = client.subscribe(
          runId,
          cursorRef.current,
          (value) => {
            if (disposedRef.current) return;
            if ('payload' in value && 'sequence' in value) {
              mergeEvent(value as StoredEvent);
            } else {
              attemptRef.current = 0;
              applySnapshot(value as RunSnapshot);
            }
          },
          () => {
            teardownSubscription();
            if (disposedRef.current) return;
            if (!_ACTIVE_PHASES.has(phaseRef.current)) return;
            scheduleReconnect();
          },
        );
      } catch (caught) {
        if (disposedRef.current) return;
        setError(caught);
        scheduleReconnect();
      }
    };

    void connect();

    return () => {
      disposedRef.current = true;
      clearTimer();
      teardownSubscription();
    };
  }, [runId, client]);

  const refresh = useCallback(() => refreshRef.current(), []);

  return { snapshot, events, error, refresh };
}
