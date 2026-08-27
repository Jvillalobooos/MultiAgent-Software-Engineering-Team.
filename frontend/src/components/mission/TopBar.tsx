import React from 'react';
import { motion } from 'framer-motion';
import { ActivityIcon, HexagonIcon, RadioIcon, TimerIcon } from 'lucide-react';
import { RunStatus } from '../../types/mission';
import { STATUS_THEME, formatElapsed } from '../../utils/format';

interface TopBarProps {
  runId: string;
  elapsed: number;
  iteration: number;
  maxIterations: number;
  status: RunStatus;
  projectPath: string;
  writeMode: 'dry_run' | 'authorized';
}

const Metric = ({
  icon,
  label,
  children




}: {icon: React.ReactNode;label: string;children: React.ReactNode;}) =>
<div className="flex items-center gap-2.5">
    <span className="text-mist/70">{icon}</span>
    <div className="leading-tight">
      <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-mist/60">{label}</div>
      <div className="font-mono text-sm text-slate-100">{children}</div>
    </div>
  </div>;


export function TopBar({
  runId,
  elapsed,
  iteration,
  maxIterations,
  status,
  projectPath,
  writeMode
}: TopBarProps) {
  const theme = STATUS_THEME[status];
  const running = status === 'RUNNING';

  return (
    <header className="glass relative z-20 flex flex-wrap items-center gap-x-8 gap-y-4 border-x-0 border-t-0 px-5 py-3.5 md:px-7">
      <div className="flex items-center gap-3">
        <div className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-electric/40 bg-electric/10">
          <HexagonIcon className="h-4 w-4 text-electric" strokeWidth={2.2} />
        </div>
        <div className="leading-tight">
          <h1 className="text-sm font-semibold tracking-tight text-slate-50">Mission Control</h1>
          <p className="font-mono text-[11px] text-mist/70">{projectPath}</p>
        </div>
      </div>

      <div className="hidden h-8 w-px bg-hull-400/50 md:block" />

      <Metric icon={<RadioIcon className="h-4 w-4" />} label="Run ID">
        {runId}
      </Metric>
      <Metric icon={<TimerIcon className="h-4 w-4" />} label="Elapsed">
        <span className="tabular-nums">{formatElapsed(elapsed)}</span>
      </Metric>
      <Metric icon={<ActivityIcon className="h-4 w-4" />} label="Iteration">
        {iteration}/{maxIterations}
      </Metric>

      <div className="ml-auto flex items-center gap-3">
        <span
          className={`hidden rounded-md border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.16em] sm:inline-block ${
          writeMode === 'authorized' ?
          'border-alert/40 bg-alert/10 text-alert' :
          'border-amber/40 bg-amber/10 text-amber'}`
          }>
          
          {writeMode === 'authorized' ? 'writes authorized' : 'dry run'}
        </span>
        <motion.div
          layout
          transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}
          className={`flex items-center gap-2 rounded-md border px-3 py-1.5 ${theme.border} ${theme.bg} ${theme.shadow}`}>
          
          <span className="relative flex h-2 w-2">
            {running &&
            <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${theme.dot} opacity-70`} />
            }
            <span className={`relative inline-flex h-2 w-2 rounded-full ${theme.dot}`} />
          </span>
          <span className={`font-mono text-[11px] font-medium tracking-[0.14em] ${theme.text}`}>
            {theme.label}
          </span>
        </motion.div>
      </div>
    </header>);

}