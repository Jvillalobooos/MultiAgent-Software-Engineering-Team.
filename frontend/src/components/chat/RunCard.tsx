import { useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { RunClient } from '../../api/runClient';
import { usePersistentRun } from '../../hooks/usePersistentRun';
import { AgentId, Provider, RunPhase } from '../../types/mission';
import { AgentGraph } from '../mission/AgentGraph';
import { ActionTicker } from '../mission/ActionTicker';
import { MissionDebrief } from '../debrief/MissionDebrief';

interface RunCardProps {
  runId: string;
  client: RunClient;
}

/** Every phase label and every gated section (graph, ticker, debrief, diff,
 *  apply, restore) is a pure function of the persisted RunSnapshot — nothing
 *  here is inferred or invented client-side. */
export const PHASE_LABEL: Record<RunPhase, string> = {
  queued: 'Queued',
  preparing: 'Preparing workspace',
  running: 'Agents working',
  review_required: 'Review required',
  approved: 'Approved',
  failed: 'Failed',
  applying: 'Applying changes',
  applied: 'Applied',
  apply_failed: 'Apply failed',
};

const PHASE_BADGE_CLASS: Record<RunPhase, string> = {
  queued: 'border-hull-400/55 text-mist/70',
  preparing: 'border-electric/45 bg-electric/10 text-electric',
  running: 'border-electric/45 bg-electric/10 text-electric',
  review_required: 'border-amber/45 bg-amber/10 text-amber',
  approved: 'border-neon/45 bg-neon/10 text-neon',
  failed: 'border-alert/45 bg-alert/10 text-alert',
  applying: 'border-electric/45 bg-electric/10 text-electric',
  applied: 'border-neon/45 bg-neon/10 text-neon',
  apply_failed: 'border-alert/45 bg-alert/10 text-alert',
};

type Banner = { kind: 'error' | 'success'; text: string };

export function RunCard({ runId, client }: RunCardProps) {
  const { snapshot, events, refresh } = usePersistentRun(runId, client);
  const [confirming, setConfirming] = useState(false);
  const [applyPending, setApplyPending] = useState(false);
  const [restorePending, setRestorePending] = useState(false);
  const [banner, setBanner] = useState<Banner | null>(null);

  if (!snapshot) {
    return (
      <article aria-label={`Run ${runId}`} className="glass flex items-center gap-3 rounded-2xl p-5 shadow-panel">
        <LoaderCircleIcon className="h-4 w-4 animate-spin text-electric" />
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-mist/60">Loading run…</span>
      </article>);

  }

  const { phase, report, apply_result, project_path, message, changed_paths } = snapshot;
  const runEvents = events.map((event) => event.payload);

  const showGraph = phase === 'preparing' || phase === 'running';
  const showDebrief = report !== null;
  const canApply = phase === 'approved' && report?.workspace_changed === true;
  const canRestore = apply_result?.status === 'apply_failed' && Boolean(apply_result.backup_path);

  const providers = Object.create(null) as Record<AgentId, Provider | null>;
  const lastEvent = runEvents[runEvents.length - 1];

  const handleApplyConfirmed = async () => {
    setApplyPending(true);
    setBanner(null);
    try {
      const result = await client.apply(runId, project_path);
      if (result.status === 'conflict' || result.status === 'apply_failed') {
        setBanner({ kind: 'error', text: result.message });
      } else {
        setBanner({ kind: 'success', text: result.message });
      }
    } catch (caught) {
      setBanner({ kind: 'error', text: caught instanceof Error ? caught.message : 'Apply failed' });
    } finally {
      setApplyPending(false);
      setConfirming(false);
      // The backend has already persisted the new phase and apply_result -- the
      // websocket may be closed by now (phase left the active set), so nothing
      // else will push this update. Re-fetch so the card reflects durable state.
      await refresh();
    }
  };

  const handleRestore = async () => {
    setRestorePending(true);
    try {
      const result = await client.restore(runId);
      setBanner({ kind: result.status === 'restored' ? 'success' : 'error', text: result.message });
    } catch (caught) {
      setBanner({ kind: 'error', text: caught instanceof Error ? caught.message : 'Restore failed' });
    } finally {
      setRestorePending(false);
      await refresh();
    }
  };

  return (
    <article aria-label={`Run ${runId}`} className="glass flex flex-col gap-4 rounded-2xl p-5 shadow-panel">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold tracking-tight text-slate-100">{message}</h3>
          <p className="mt-0.5 truncate font-mono text-[11px] text-mist/60">{project_path}</p>
        </div>
        <span
          data-testid="run-phase-badge"
          className={`shrink-0 rounded-md border px-3 py-1 font-mono text-[11px] uppercase tracking-[0.14em] ${PHASE_BADGE_CLASS[phase]}`}>

          {PHASE_LABEL[phase]}
        </span>
      </header>

      {showGraph &&
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div className="min-h-[280px] overflow-x-auto rounded-xl border border-hull-400/35 bg-hull-800/40 p-3">
            <AgentGraph
            activeAgent={lastEvent ? lastEvent.agent : null}
            caption={lastEvent ? lastEvent.status_message : ''}
            providers={providers}
            fallbacks={{}}
            activeEdge={null}
            visitedEdges={[]}
            dimmed={false} />

          </div>
          <ActionTicker events={runEvents} />
        </div>
      }

      {showDebrief && report &&
      <MissionDebrief report={report} runId={runId} projectPath={project_path} />
      }

      {apply_result &&
      <section
        aria-label="Apply result"
        className="flex flex-col gap-2 rounded-xl border border-hull-400/35 bg-hull-800/40 p-3">
          <h4 className="font-mono text-[11px] uppercase tracking-[0.14em] text-mist/70">
            Apply result: {apply_result.status}
          </h4>
          <p className="font-mono text-[11.5px] leading-snug text-slate-200">{apply_result.message}</p>
          {apply_result.written_paths.length > 0 &&
          <p className="font-mono text-[11px] text-mist/70">
              Written: {apply_result.written_paths.join(', ')}
            </p>
          }
          {apply_result.test_exit_code !== null &&
          <p className="font-mono text-[11px] text-mist/70">
              Test exit code: {apply_result.test_exit_code}
            </p>
          }
          {apply_result.test_output &&
          <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap rounded-md border border-hull-400/30 bg-hull-900/50 p-2 font-mono text-[10.5px] text-mist/70">
              {apply_result.test_output.slice(-2000)}
            </pre>
          }
          <p className="font-mono text-[11px] text-mist/70">
            Backup: {apply_result.backup_path ? 'available' : 'none'}
          </p>
        </section>
      }

      {(canApply || canRestore) &&
      <div className="flex flex-col gap-3 border-t border-hull-400/30 pt-4">
          {canApply &&
        <div className="flex flex-col gap-3">
              {!confirming ?
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="w-fit rounded-md border border-electric/50 bg-electric/15 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-slate-50 hover:bg-electric/25">

                  Apply
                </button> :

          <div role="group" aria-label="Confirm apply" className="glass-soft flex flex-col gap-3 rounded-lg p-4">
                  <p className="font-mono text-[11.5px] leading-snug text-slate-200">
                    Apply {changed_paths.length} change{changed_paths.length === 1 ? '' : 's'} to{' '}
                    <span className="text-electric">{project_path}</span>? Affected:{' '}
                    {changed_paths.join(', ')}
                  </p>
                  <div className="flex gap-2">
                    <button
              type="button"
              disabled={applyPending}
              onClick={handleApplyConfirmed}
              className="rounded-md border border-electric/50 bg-electric/15 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-slate-50 hover:bg-electric/25 disabled:opacity-50">

                      Confirm apply
                    </button>
                    <button
              type="button"
              disabled={applyPending}
              onClick={() => setConfirming(false)}
              className="rounded-md border border-hull-400/55 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-mist/80 hover:text-slate-100">

                      Cancel
                    </button>
                  </div>
                </div>
          }
            </div>
        }

          {canRestore &&
        <button
          type="button"
          disabled={restorePending}
          onClick={handleRestore}
          className="w-fit rounded-md border border-amber/50 bg-amber/10 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-amber hover:bg-amber/20 disabled:opacity-50">

              Restore
            </button>
        }
        </div>
      }

      {banner &&
      <p
        role={banner.kind === 'error' ? 'alert' : 'status'}
        className={`rounded-md border px-3 py-2 font-mono text-[11px] ${
        banner.kind === 'error' ?
        'border-alert/45 bg-alert/10 text-alert' :
        'border-neon/45 bg-neon/10 text-neon'}`
        }>

          {banner.text}
        </p>
      }
    </article>);

}
