import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useRunGraph } from './useRunGraph';
import { AgentId, RunEvent } from '../types/mission';

const event = (
  agent: AgentId,
  overrides: Partial<RunEvent> = {},
): RunEvent => ({
  id: `${agent}-${Math.random()}`,
  name: 'step',
  type: 'model',
  level: 'info',
  status_message: `${agent} working`,
  metadata: {},
  agent,
  iteration: 0,
  at: 1,
  ...overrides,
});

describe('useRunGraph', () => {
  it('derives the walked route, visited edges and the current hop from real events', () => {
    const { result } = renderHook(() =>
      useRunGraph([
        event('product'),
        event('architecture'),
        event('developer'),
        event('security'),
      ]),
    );

    expect(result.current.route.map((hop) => hop.agent)).toEqual([
      'product', 'architecture', 'developer', 'security',
    ]);
    expect(result.current.visitedEdges).toEqual([
      'product-architecture', 'architecture-developer', 'developer-security',
    ]);
    expect(result.current.activeAgent).toBe('security');
    expect(result.current.activeEdge).toMatchObject({
      from: 'developer', to: 'security', kind: 'forward',
    });
  });

  it('marks a reviewer remediation loop as a reject hop so it reads as a loop, not progress', () => {
    const { result } = renderHook(() =>
      useRunGraph([
        event('testing'),
        event('reviewer'),
        event('developer', { iteration: 1 }),
      ]),
    );

    const last = result.current.route.at(-1);
    expect(last).toMatchObject({ agent: 'developer', kind: 'reject', iteration: 1 });
    expect(result.current.activeEdge).toMatchObject({ kind: 'reject' });
    expect(result.current.iteration).toBe(1);
  });

  it('records the provider actually used and flags a model fallback only when one happened', () => {
    const { result } = renderHook(() =>
      useRunGraph([
        event('product', {
          metadata: { provider: 'google', requested_model: 'gemini-3.6-flash', actual_model: 'gemini-3.6-flash' },
        }),
        event('architecture', {
          // The requested model failed and a later one answered: a real fallback.
          metadata: { provider: 'groq', requested_model: 'gemini-3.6-flash', actual_model: 'openai/gpt-oss-120b' },
        }),
        event('developer', { metadata: { provider: 'ollama' } }),
      ]),
    );

    expect(result.current.providers.product).toBe('cloud');
    expect(result.current.providers.architecture).toBe('cloud');
    expect(result.current.providers.developer).toBe('local');
    expect(result.current.fallbacks).toEqual({ architecture: 'openai/gpt-oss-120b' });
  });

  it('keeps a transition with no drawn edge as a route hop instead of dropping it', () => {
    const { result } = renderHook(() =>
      useRunGraph([event('product'), event('reviewer')]),
    );

    expect(result.current.route.map((hop) => hop.agent)).toEqual(['product', 'reviewer']);
    expect(result.current.route.at(-1)).toMatchObject({ edgeId: null, kind: null });
    expect(result.current.activeEdge).toBeNull();
    expect(result.current.visitedEdges).toEqual([]);
  });

  it('returns an inert state for a run that has not emitted anything yet', () => {
    const { result } = renderHook(() => useRunGraph([]));

    expect(result.current.activeAgent).toBeNull();
    expect(result.current.activeEdge).toBeNull();
    expect(result.current.route).toEqual([]);
    expect(result.current.caption).toBe('');
  });
});
