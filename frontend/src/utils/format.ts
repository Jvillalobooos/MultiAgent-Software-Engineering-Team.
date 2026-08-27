import { AgentId, EdgeKind, RunStatus, ToolStatus } from '../types/mission';

export const formatElapsed = (ms: number): string => {
  const total = Math.max(0, ms);
  const minutes = Math.floor(total / 60000);
  const seconds = Math.floor(total % 60000 / 1000);
  const tenths = Math.floor(total % 1000 / 100);
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${tenths}`;
};

export const formatClock = (at: number): string => {
  const d = new Date(at);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(
    d.getSeconds()
  ).padStart(2, '0')}`;
};

export const AGENT_LABELS: Record<AgentId, string> = {
  product: 'Product',
  architecture: 'Architecture',
  developer: 'Developer',
  security: 'Security',
  testing: 'Testing',
  reviewer: 'Reviewer',
  human_review: 'Human Review'
};

interface StatusTheme {
  label: string;
  text: string;
  border: string;
  bg: string;
  dot: string;
  shadow: string;
}

export const STATUS_THEME: Record<RunStatus, StatusTheme> = {
  RUNNING: {
    label: 'RUNNING',
    text: 'text-electric',
    border: 'border-electric/50',
    bg: 'bg-electric/10',
    dot: 'bg-electric',
    shadow: 'shadow-glow-electric'
  },
  APPROVED: {
    label: 'APPROVED',
    text: 'text-neon',
    border: 'border-neon/50',
    bg: 'bg-neon/10',
    dot: 'bg-neon',
    shadow: 'shadow-glow-neon'
  },
  REJECTED: {
    label: 'REJECTED',
    text: 'text-alert',
    border: 'border-alert/50',
    bg: 'bg-alert/10',
    dot: 'bg-alert',
    shadow: 'shadow-glow-alert'
  },
  HUMAN_REVIEW_REQUIRED: {
    label: 'HUMAN_REVIEW_REQUIRED',
    text: 'text-amber',
    border: 'border-amber/50',
    bg: 'bg-amber/10',
    dot: 'bg-amber',
    shadow: 'shadow-glow-amber'
  }
};

export const EDGE_COLOR: Record<EdgeKind, string> = {
  forward: '#3fb6ff',
  reject: '#ff8f4d',
  branch: '#ffb545'
};

export const TOOL_STATUS_CLASS: Record<ToolStatus, string> = {
  SUCCESS: 'text-neon border-neon/40 bg-neon/10',
  FAIL: 'text-alert border-alert/40 bg-alert/10',
  DENIED: 'text-amber border-amber/40 bg-amber/10'
};