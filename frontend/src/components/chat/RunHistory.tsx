import { forwardRef, useMemo, useState } from 'react';
import { ChevronRightIcon, HistoryIcon, LayersIcon, RotateCcwIcon, SearchIcon, XIcon } from 'lucide-react';
import { RunPhase, RunSummary } from '../../types/mission';
import { formatRelative, formatTimestamp, projectName, shortTrace } from '../../utils/format';
import { PHASE_LABEL } from './RunCard';

interface RunHistoryProps {
  summaries: RunSummary[];
  activeRunId: string | null;
  onOpenRun: (runId: string) => void;
  /** Load a past instruction back into the composer without launching it. */
  onReuse: (summary: RunSummary) => void;
}

/** One logical execution plus every retry of it, newest attempt first. */
export interface RunGroup {
  key: string;
  message: string;
  projectPath: string;
  attempts: RunSummary[];
}

const PHASE_DOT: Record<RunPhase, string> = {
  queued: 'bg-mist/50',
  preparing: 'bg-electric',
  running: 'bg-electric',
  review_required: 'bg-amber',
  approved: 'bg-neon',
  failed: 'bg-alert',
  applying: 'bg-electric',
  applied: 'bg-neon',
  apply_failed: 'bg-alert',
};

const PHASE_TEXT: Record<RunPhase, string> = {
  queued: 'text-mist',
  preparing: 'text-electric',
  running: 'text-electric',
  review_required: 'text-amber',
  approved: 'text-neon',
  failed: 'text-alert',
  applying: 'text-electric',
  applied: 'text-neon',
  apply_failed: 'text-alert',
};

const IN_FLIGHT = new Set<RunPhase>(['queued', 'preparing', 'running', 'applying']);

/** Retries of one execution are the runs that re-issue the *same instruction against
 *  the same project*. That pair is the only stable identity the run record carries —
 *  a fresh run_id is minted per attempt — so it is what collapses history into one
 *  row per execution instead of one row per attempt. */
export function groupRuns(summaries: RunSummary[]): RunGroup[] {
  const groups = new Map<string, RunGroup>();
  for (const summary of summaries) {
    const key = `${summary.project_path}\u0000${summary.message}`;
    const existing = groups.get(key);
    if (existing) {
      existing.attempts.push(summary);
    } else {
      groups.set(key, {
        key,
        message: summary.message,
        projectPath: summary.project_path,
        attempts: [summary],
      });
    }
  }
  const byNewest = (a: RunSummary, b: RunSummary) =>
    new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  return [...groups.values()]
    .map((group) => ({ ...group, attempts: [...group.attempts].sort(byNewest) }))
    .sort((a, b) => byNewest(a.attempts[0], b.attempts[0]));
}

function PhaseChip({ phase }: { phase: RunPhase }) {
  return (
    <span className={`flex shrink-0 items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] ${PHASE_TEXT[phase]}`}>
      <span
        className={`h-1.5 w-1.5 rounded-full ${PHASE_DOT[phase]} ${IN_FLIGHT.has(phase) ? 'animate-pulse' : ''}`}
        aria-hidden="true" />
      {PHASE_LABEL[phase]}
    </span>
  );
}

function GroupRow({ group, activeRunId, onOpenRun, onReuse }: {
  group: RunGroup;
  activeRunId: string | null;
  onOpenRun: (runId: string) => void;
  onReuse: (summary: RunSummary) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const latest = group.attempts[0];
  const retries = group.attempts.length - 1;
  const isActive = group.attempts.some((attempt) => attempt.run_id === activeRunId);

  return (
    <li className={`glass-soft shrink-0 overflow-hidden rounded-lg transition-colors ${isActive ? 'border-electric/45' : ''}`}>
      <div className="flex items-stretch">
        <button
          type="button"
          onClick={() => onOpenRun(latest.run_id)}
          aria-current={isActive ? 'true' : undefined}
          aria-label={`Open run: ${group.message}`}
          className="flex min-w-0 flex-1 flex-col gap-1.5 px-3 py-2.5 text-left transition-colors hover:bg-hull-600/40 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-electric">
          <div className="flex items-center gap-2">
            <PhaseChip phase={latest.phase} />
            <span className="ml-auto shrink-0 font-mono text-[10px] text-mist/80" title={formatTimestamp(latest.created_at)}>
              {formatRelative(latest.created_at)}
            </span>
          </div>
          <p className="line-clamp-2 text-[13px] leading-snug text-slate-100">{group.message}</p>
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-[10px] text-mist/80">
            <span className="truncate" title={group.projectPath}>{projectName(group.projectPath)}</span>
            {latest.trace_id && (
              <span className="text-plasma/75" title={`Trace ${latest.trace_id}`}>
                trace {shortTrace(latest.trace_id)}
              </span>
            )}
          </div>
        </button>

        <button
          type="button"
          onClick={() => onReuse(latest)}
          aria-label={`Reuse this instruction: ${group.message.slice(0, 60)}`}
          title="Load this instruction into the composer"
          className="flex shrink-0 items-center border-l border-hull-400/30 px-2.5 text-mist transition-colors hover:bg-hull-600/40 hover:text-electric focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-electric">
          <RotateCcwIcon aria-hidden="true" className="h-3.5 w-3.5" />
        </button>

        {retries > 0 && (
          <button
            type="button"
            onClick={() => setExpanded((open) => !open)}
            aria-expanded={expanded}
            aria-label={`${group.attempts.length} attempts of this run`}
            className="flex shrink-0 items-center gap-1.5 border-l border-hull-400/30 px-2.5 font-mono text-[10px] uppercase tracking-[0.1em] text-amber transition-colors hover:bg-hull-600/40 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-electric">
            <LayersIcon aria-hidden="true" className="h-3 w-3" />
            ×{group.attempts.length}
            <ChevronRightIcon
              aria-hidden="true"
              className={`h-3 w-3 transition-transform duration-200 ease-command ${expanded ? 'rotate-90' : ''}`} />
          </button>
        )}
      </div>

      {expanded && retries > 0 && (
        <ul className="border-t border-hull-400/25 bg-hull-900/40">
          {group.attempts.map((attempt, index) => (
            <li key={attempt.run_id}>
              <button
                type="button"
                onClick={() => onOpenRun(attempt.run_id)}
                className={`flex w-full items-center gap-2.5 px-3 py-2 text-left font-mono text-[10px] transition-colors hover:bg-hull-600/40 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-electric ${
                  attempt.run_id === activeRunId ? 'bg-electric/10' : ''}`}>
                <span className="w-[76px] shrink-0 uppercase tracking-[0.1em] text-mist/80">
                  {index === 0 ? 'latest' : `attempt ${group.attempts.length - index}`}
                </span>
                <PhaseChip phase={attempt.phase} />
                <span className="ml-auto shrink-0 text-mist/80" title={formatTimestamp(attempt.created_at)}>
                  {formatRelative(attempt.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** History is a *navigator*, not a feed: it renders one row per execution and never
 *  mounts a run's live subscription, so restarting the backend can no longer stack
 *  every past run on the screen at once. */
export const RunHistory = forwardRef<HTMLInputElement, RunHistoryProps>(function RunHistory(
  { summaries, activeRunId, onOpenRun, onReuse }, filterRef,
) {
  const [query, setQuery] = useState('');
  const allGroups = useMemo(() => groupRuns(summaries), [summaries]);
  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return allGroups;
    return allGroups.filter((group) =>
      group.message.toLowerCase().includes(needle) ||
      group.projectPath.toLowerCase().includes(needle));
  }, [allGroups, query]);

  return (
    <section aria-label="Run history" className="glass flex min-h-0 flex-col rounded-2xl shadow-panel">
      <div className="flex items-center gap-2 border-b border-hull-400/35 px-4 py-3">
        <HistoryIcon aria-hidden="true" className="h-3.5 w-3.5 text-electric" />
        <h2 className="text-[12px] font-semibold tracking-tight text-slate-100">Run history</h2>
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.14em] text-mist/80">
          {query ?
            `${groups.length} of ${allGroups.length}` :
            `${groups.length} execution${groups.length === 1 ? '' : 's'}`}
        </span>
      </div>

      {allGroups.length > 0 && (
        <div className="relative border-b border-hull-400/25 px-3 py-2">
          <SearchIcon
            aria-hidden="true"
            className="pointer-events-none absolute left-5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-mist" />
          <input
            ref={filterRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Filter runs by instruction or project"
            placeholder="Filter runs…"
            className="h-9 w-full rounded-md border border-hull-400/55 bg-hull-800/60 pl-8 pr-16 font-mono text-[11px] text-slate-100 outline-none placeholder:text-mist focus:border-electric focus:ring-1 focus:ring-electric" />
          {query ? (
            <button
              type="button"
              onClick={() => setQuery('')}
              aria-label="Clear filter"
              className="absolute right-5 top-1/2 -translate-y-1/2 rounded p-1 text-mist transition-colors hover:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-electric">
              <XIcon aria-hidden="true" className="h-3.5 w-3.5" />
            </button>
          ) : (
            <kbd className="pointer-events-none absolute right-5 top-1/2 -translate-y-1/2 rounded border border-hull-400/55 px-1.5 py-0.5 font-mono text-[10px] text-mist">
              /
            </kbd>
          )}
        </div>
      )}

      {groups.length === 0 ? (
        <p className="px-4 py-8 text-center font-mono text-[11px] text-mist/80">
          {query ?
            <>No run matches <span className="text-slate-200">{query}</span>.</> :
            'No runs yet. Your executions will be listed here.'}
        </p>
      ) : (
        <ul className="thin-scroll flex max-h-[420px] flex-col gap-1.5 overflow-y-auto p-3">
          {groups.map((group) => (
            <GroupRow
              key={group.key}
              group={group}
              activeRunId={activeRunId}
              onOpenRun={onOpenRun}
              onReuse={onReuse} />
          ))}
        </ul>
      )}
    </section>
  );
});
