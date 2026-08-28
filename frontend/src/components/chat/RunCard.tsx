import { useMemo, useState } from 'react';
import { HashIcon, LoaderCircleIcon } from 'lucide-react';
import { RunClient } from '../../api/runClient';
import { usePersistentRun } from '../../hooks/usePersistentRun';
import { RunPhase } from '../../types/mission';
import { AGENT_LABELS, formatDuration, formatTimestamp, shortTrace } from '../../utils/format';
import { useRunGraph } from '../../hooks/useRunGraph';
import { AgentGraph } from '../mission/AgentGraph';
import { RouteTrace } from '../mission/RouteTrace';
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

/** What each phase means and what it asks of the operator, in plain language. */
const PHASE_GUIDANCE: Record<RunPhase, string> = {
  queued: 'Waiting for a worker. Nothing has run yet and your project is untouched.',
  preparing: 'Copying your project to an isolated workspace. Your files are not being read by the agents yet.',
  running: 'The six agents are working on the copy. Your project stays untouched until you approve.',
  review_required: 'The reviewer did not approve. Read the scorecard below for what failed, then reuse this instruction with more detail and run it again.',
  approved: 'The reviewer approved the change. Nothing has been written yet — press Apply to write it to your project.',
  failed: 'The run stopped before producing a result. The errors tab lists what broke. Your project is unchanged.',
  applying: 'Writing the approved files to your project and running your tests against them.',
  applied: 'The change is now in your project and the tests were run against it. A backup was kept.',
  apply_failed: 'The write was attempted and did not verify. Check the apply result below; Restore returns your project to its previous state.',
};

const PHASE_BADGE_CLASS: Record<RunPhase, string> = {
  queued: 'border-hull-400/55 text-mist',
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

/** One measured fact about the run. Every value here is read from the persisted
 *  snapshot or its recorded events — nothing is estimated client-side. */
function Metric({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="min-w-0">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-mist/80">{label}</div>
      <div className={`mt-0.5 truncate font-mono text-[12px] tabular-nums ${accent ?? 'text-slate-100'}`}>
        {value}
      </div>
    </div>
  );
}


export function RunCard({ runId, client }: RunCardProps) {
  const { snapshot, events, refresh } = usePersistentRun(runId, client);
  const runEvents = useMemo(() => events.map((event) => event.payload), [events]);
  const graph = useRunGraph(runEvents);
  const [confirming, setConfirming] = useState(false);
  const [applyPending, setApplyPending] = useState(false);
  const [restorePending, setRestorePending] = useState(false);
  const [banner, setBanner] = useState<Banner | null>(null);

  if (!snapshot) {
    return (
      <article aria-label={`Run ${runId}`} className="glass flex items-center gap-3 rounded-2xl p-5 shadow-panel">
        <LoaderCircleIcon className="h-4 w-4 animate-spin text-electric" />
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-mist/80">Loading run…</span>
      </article>);

  }

  const { phase, report, apply_result, project_path, message, changed_paths } = snapshot;

  const showGraph = phase === 'preparing' || phase === 'running';
  const showDebrief = report !== null;
  const canApply = phase === 'approved' && report?.workspace_changed === true;
  const canRestore = apply_result?.status === 'apply_failed' && Boolean(apply_result.backup_path);


  // Every metric below is counted from what was actually recorded for this run.
  const traceLabel = snapshot.trace_id ?? runId;
  const activeAgent = graph.activeAgent;
  const iteration = report ? report.route_history.length : graph.iteration;
  const modelCalls = report
    ? report.model_usage.reduce((sum, usage) => sum + usage.calls, 0)
    : runEvents.filter((event) => event.type === 'model').length;
  const totalTokens = report
    ? report.model_usage.reduce((sum, usage) => sum + usage.input_tokens + usage.output_tokens, 0)
    : runEvents.reduce(
        (sum, event) =>
          sum + (event.usage_details
            ? event.usage_details.input_tokens + event.usage_details.output_tokens
            : 0),
        0,
      );
  const toolCalls = report
    ? report.tool_results.length
    : runEvents.filter((event) => event.type === 'tool').length;
  const ragHits = report
    ? report.rag_evidence.length
    : runEvents.filter((event) => event.type === 'rag').length;
  const errorCount = report
    ? report.errors.length
    : runEvents.filter((event) => event.type === 'error' && event.level === 'error').length;

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
    <article aria-label={`Run ${runId}`} className="glass flex flex-col gap-4 rounded-2xl border-l-[3px] border-l-electric/60 p-5 shadow-panel">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p
            data-testid="run-trace-id"
            aria-label="Run trace id"
            title={traceLabel}
            className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-electric/80">

            <HashIcon aria-hidden="true" className="h-3 w-3" />
            trace {shortTrace(traceLabel)}
            {snapshot.trace_id ? null : <span className="text-mist/80">· pending</span>}
          </p>
          <h2 className="mt-1 break-words text-sm font-semibold leading-snug tracking-tight text-slate-100">{message}</h2>
          <p className="mt-0.5 truncate font-mono text-[11px] text-mist/80">{project_path}</p>
          <p aria-label="Run write permission" className="mt-2 text-xs text-mist">
            {snapshot.authorize_writes === true ? 'Writes authorized · --authorize-writes'
              : snapshot.authorize_writes === false ? 'Automatic writes not authorized · --dry-run'
              : 'Write permission not recorded · legacy run'}
          </p>
        </div>
        <span
          data-testid="run-phase-badge"
          className={`shrink-0 rounded-md border px-3 py-1 font-mono text-[11px] uppercase tracking-[0.14em] ${PHASE_BADGE_CLASS[phase]}`}>

          {PHASE_LABEL[phase]}
        </span>

        <p className="w-full text-[12px] leading-relaxed text-mist">
          {PHASE_GUIDANCE[phase]}
        </p>
      </header>

      <section
        aria-label="Run metrics"
        className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-xl border border-hull-400/35 bg-hull-800/40 px-4 py-3 sm:grid-cols-4 lg:grid-cols-8">

        <Metric label="started" value={formatTimestamp(snapshot.created_at)} />
        <Metric label="duration" value={formatDuration(snapshot.created_at, snapshot.updated_at)} />
        <Metric label="stage" value={activeAgent ? AGENT_LABELS[activeAgent] : '—'} accent="text-electric" />
        <Metric label="iteration" value={String(iteration)} />
        <Metric label="events" value={String(runEvents.length)} />
        <Metric label="model calls" value={`${modelCalls}${totalTokens ? ` · ${totalTokens.toLocaleString()} tok` : ''}`} />
        <Metric label="tools / rag" value={`${toolCalls} / ${ragHits}`} />
        <Metric
          label="errors"
          value={String(errorCount)}
          accent={errorCount > 0 ? 'text-alert' : 'text-mist'} />

      </section>

      {snapshot.test_spec && (
        <details className="rounded-lg border border-hull-400/50 bg-hull-800/40 px-3 py-2 text-sm">
          <summary className="cursor-pointer rounded py-1 text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric">Test specification</summary>
          <p className="mt-2 whitespace-pre-wrap break-words leading-relaxed text-slate-200">{snapshot.test_spec}</p>
        </details>
      )}

      {showGraph &&
      <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <div className="min-h-[280px] overflow-x-auto rounded-xl border border-hull-400/35 bg-hull-800/40 p-3">
              <AgentGraph
              activeAgent={graph.activeAgent}
              visitedAgents={graph.visitedAgents}
              caption={graph.caption}
              providers={graph.providers}
              fallbacks={graph.fallbacks}
              activeEdge={graph.activeEdge}
              visitedEdges={graph.visitedEdges}
              dimmed={false} />

            </div>
            <ActionTicker events={runEvents} />
          </div>
          <RouteTrace route={graph.route} />
        </div>
      }

      {!showGraph && runEvents.length > 0 &&
      <details className="rounded-xl border border-hull-400/35 bg-hull-800/40 px-3 py-2">
          <summary className="cursor-pointer rounded py-1 font-mono text-[11px] uppercase tracking-[0.12em] text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric">
            Execution timeline · {runEvents.length} events
          </summary>
          <div className="mt-2">
            <ActionTicker events={runEvents} />
          </div>
        </details>
      }

      {showDebrief && report &&
      <MissionDebrief report={report} runId={runId} traceId={snapshot.trace_id} projectPath={project_path} applyResult={apply_result} phase={phase} />
      }

      {apply_result &&
      <section
        aria-label="Apply result"
        className="flex flex-col gap-2 rounded-xl border border-hull-400/35 bg-hull-800/40 p-3">
          <h3 className="font-mono text-[11px] uppercase tracking-[0.14em] text-mist">
            Apply result: {apply_result.status}
          </h3>
          <p className="font-mono text-[11px] leading-snug text-slate-200">{apply_result.message}</p>
          {apply_result.written_paths.length > 0 &&
          <p className="font-mono text-[11px] text-mist">
              Written: {apply_result.written_paths.join(', ')}
            </p>
          }
          {apply_result.test_exit_code !== null &&
          <p className="font-mono text-[11px] text-mist">
              Test exit code: {apply_result.test_exit_code}
            </p>
          }
          {apply_result.test_output &&
          <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap rounded-md border border-hull-400/30 bg-hull-900/50 p-2 font-mono text-[10px] text-mist">
              {apply_result.test_output.slice(-2000)}
            </pre>
          }
          <p className="font-mono text-[11px] text-mist">
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
                  <p className="font-mono text-[11px] leading-snug text-slate-200">
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
