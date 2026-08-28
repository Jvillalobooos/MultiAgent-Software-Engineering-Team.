import { ComponentProps } from 'react';
import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AgentGraph } from './AgentGraph';

const noop = () => undefined;

/** jsdom has no matchMedia; each test installs the answer it needs. */
function mockReducedMotion(reduce: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduce,
    media: query,
    addEventListener: noop,
    removeEventListener: noop,
    // framer-motion still probes the legacy MediaQueryList API.
    addListener: noop,
    removeListener: noop,
  }));
}

const props: ComponentProps<typeof AgentGraph> = {
  activeAgent: 'developer',
  visitedAgents: ['product', 'architecture'],
  caption: 'applying reviewer feedback',
  providers: {
    product: 'cloud', architecture: 'cloud', developer: 'local',
    security: null, testing: null, reviewer: null, human_review: null,
  },
  fallbacks: {},
  activeEdge: {
    key: 3, from: 'architecture', to: 'developer', kind: 'forward', duration: 1200,
  },
  visitedEdges: ['product-architecture', 'architecture-developer'],
  dimmed: false,
};

afterEach(() => vi.unstubAllGlobals());

describe('AgentGraph', () => {
  it('streams particles continuously along the active edge', () => {
    mockReducedMotion(false);
    const { container } = render(<AgentGraph {...props} />);

    const motions = container.querySelectorAll('animateMotion');
    expect(motions.length).toBeGreaterThan(0);
    // A run can sit on one agent for a long time: the stream must loop, not freeze.
    motions.forEach((motion) =>
      expect(motion.getAttribute('repeatCount')).toBe('indefinite'),
    );
  });

  it('withholds the particle stream entirely when reduced motion is requested', () => {
    mockReducedMotion(true);
    const { container } = render(<AgentGraph {...props} />);

    // SMIL ignores the global reduced-motion CSS rule, so these must not be rendered.
    expect(container.querySelectorAll('animateMotion')).toHaveLength(0);
  });

  it('distinguishes an agent that already ran from one the run never reached', () => {
    mockReducedMotion(false);
    const { getByText, getAllByText } = render(<AgentGraph {...props} />);

    expect(getByText('active')).toBeInTheDocument();
    // Product and Architecture ran; Security, Testing and Reviewer did not.
    expect(getAllByText('done')).toHaveLength(2);
  });
});
