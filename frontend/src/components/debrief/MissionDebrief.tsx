import { motion } from 'framer-motion';
import { HexagonIcon } from 'lucide-react';
import { FinalReport } from '../../types/mission';
import { AGENT_LABELS, STATUS_THEME } from '../../utils/format';
import { DiffViewer } from './DiffViewer';
import { Scorecard } from './Scorecard';
import { DecisionTimeline } from './DecisionTimeline';
import { EvidenceTabs } from './EvidenceTabs';

interface MissionDebriefProps {
  report: FinalReport;
  runId: string;
  projectPath: string;
}

const ease = [0.23, 1, 0.32, 1] as const;

/** Embedded review section for a RunCard — no page-level chrome, no fixed viewport
 *  height, and no replay/new-run navigation, all of which belonged to the old
 *  standalone debrief screen. */
export function MissionDebrief({ report, runId, projectPath }: MissionDebriefProps) {
  const theme = STATUS_THEME[report.review.status];
  const totalTokens = report.model_usage.reduce(
    (sum, u) => sum + u.input_tokens + u.output_tokens,
    0
  );
  const totalCalls = report.model_usage.reduce((sum, u) => sum + u.calls, 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease }}
      className="w-full"
      aria-label="Mission debrief">

      <div className="w-full">
        <header className="glass flex flex-wrap items-center gap-x-8 gap-y-5 rounded-2xl px-6 py-5 shadow-panel">
          <div className="flex items-center gap-3">
            <div className={`flex h-10 w-10 items-center justify-center rounded-lg border ${theme.border} ${theme.bg}`}>
              <HexagonIcon className={`h-4 w-4 ${theme.text}`} strokeWidth={2.2} />
            </div>
            <div>
              <h4 className="text-sm font-semibold tracking-tight text-slate-50">Mission Debrief</h4>
              <p className="font-mono text-[11px] text-mist/70">
                {runId} · {projectPath}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-x-8 gap-y-3 font-mono text-[11px]">
            {[
            ['iterations', String(report.route_history.length)],
            ['model calls', String(totalCalls)],
            ['tokens', totalTokens.toLocaleString()],
            ['files changed', String(report.changed_files.length)]].
            map(([label, value]) =>
            <div key={label}>
                <div className="text-[9.5px] uppercase tracking-[0.16em] text-mist/50">{label}</div>
                <div className="mt-0.5 text-sm tabular-nums text-slate-100">{value}</div>
              </div>
            )}
          </div>

          <div className="ml-auto flex items-center gap-2.5">
            <span
              className={`rounded-md border px-3 py-1.5 font-mono text-[11px] tracking-[0.14em] ${theme.border} ${theme.bg} ${theme.text} ${theme.shadow}`}>

              {theme.label}
            </span>
          </div>
        </header>

        <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="flex min-h-0 flex-col gap-6">
            <div className="flex max-h-[560px] min-h-[280px] flex-col">
              <DiffViewer files={report.changed_files} applied={report.applied_diff} />
            </div>
            <EvidenceTabs
              rag={report.rag_evidence}
              tools={report.tool_results}
              errors={report.errors} />

          </div>

          <div className="flex flex-col gap-6">
            <Scorecard review={report.review} />
            <DecisionTimeline steps={report.route_history} />
            <section className="glass rounded-2xl p-5 shadow-panel" aria-label="Model usage">
              <h2 className="text-sm font-semibold tracking-tight text-slate-100">Model usage</h2>
              <ul className="mt-4 flex flex-col gap-2.5">
                {report.model_usage.map((usage) =>
                <li
                  key={`${usage.agent}-${usage.model}`}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-hull-400/25 pb-2.5 last:border-0 last:pb-0">

                    <span className="w-[92px] text-[12.5px] text-slate-200">
                      {AGENT_LABELS[usage.agent]}
                    </span>
                    <span className="font-mono text-[11px] text-mist/75">{usage.model}</span>
                    <span
                    className={`rounded border px-1.5 py-[1px] font-mono text-[9px] uppercase tracking-[0.12em] ${
                    usage.provider === 'cloud' ?
                    'border-plasma/45 bg-plasma/10 text-plasma' :
                    'border-neon/40 bg-neon/10 text-neon'}`
                    }>

                      {usage.provider}
                    </span>
                    <span className="ml-auto font-mono text-[11px] tabular-nums text-mist/80">
                      {usage.calls}× · {(usage.input_tokens + usage.output_tokens).toLocaleString()} tok ·{' '}
                      {usage.avg_latency_ms}ms
                    </span>
                  </li>
                )}
              </ul>
            </section>
          </div>
        </div>
      </div>
    </motion.div>);

}
