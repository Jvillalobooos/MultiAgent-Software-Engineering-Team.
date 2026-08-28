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

/** Absolute local timestamp for a persisted ISO date, used wherever an exact
 *  moment matters more than recency (tooltips, attempt lists). */
export const formatTimestamp = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
};

/** Coarse "how long ago" label for history rows. Deliberately low-resolution:
 *  history is for orientation, not measurement. */
export const formatRelative = (iso: string, now: number = Date.now()): string => {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 60) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days < 7 ? `${days}d ago` : formatTimestamp(iso);
};

/** Duration between two persisted ISO timestamps, as a compact label. */
export const formatDuration = (fromIso: string, toIso: string): string => {
  const from = new Date(fromIso).getTime();
  const to = new Date(toIso).getTime();
  if (Number.isNaN(from) || Number.isNaN(to) || to < from) return '—';
  const seconds = Math.round((to - from) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${String(seconds % 60).padStart(2, '0')}s`;
};

/** Trace ids are long and opaque; show enough to correlate a run with its trace
 *  in the observability backend without letting it dominate the layout. */
export const shortTrace = (traceId: string): string =>
  traceId.length <= 14 ? traceId : `${traceId.slice(0, 8)}…${traceId.slice(-4)}`;

/** Truncate free text to a bounded length on a word boundary where possible. */
export const clampText = (text: string, max: number): string => {
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const lastSpace = cut.lastIndexOf(' ');
  return `${(lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`;
};

/** The last path segment of a project path, for compact history rows. */
export const projectName = (path: string): string =>
  path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
