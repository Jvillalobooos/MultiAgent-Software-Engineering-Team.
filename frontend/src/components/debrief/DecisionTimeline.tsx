import { motion } from 'framer-motion';
import { CheckIcon, CornerUpLeftIcon } from 'lucide-react';
import { RouteStep } from '../../types/mission';
import { AGENT_LABELS } from '../../utils/format';

interface DecisionTimelineProps {
  steps: RouteStep[];
}

const ease = [0.23, 1, 0.32, 1] as const;

export function DecisionTimeline({ steps }: DecisionTimelineProps) {
  return (
    <section className="glass rounded-2xl p-5 shadow-panel" aria-label="Decision timeline">
      <h3 className="text-sm font-semibold tracking-tight text-slate-100">Decision timeline</h3>
      <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-mist/80">
        route history · {steps.length} iterations
      </p>

      <ol className="relative mt-5">
        <span className="absolute left-[13px] top-2 bottom-6 w-px bg-hull-400/50" aria-hidden />
        {steps.map((step, i) => {
          const approved = step.decision === 'APPROVED';
          const accent = approved ? 'text-neon' : 'text-alert';
          return (
            <motion.li
              key={step.iteration}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: 0.1 + i * 0.09, ease }}
              className="relative flex gap-4 pb-6 last:pb-0">
              
              <span
                className={`relative z-10 mt-0.5 flex h-[27px] w-[27px] shrink-0 items-center justify-center rounded-full border ${
                approved ?
                'border-neon/55 bg-neon/12 text-neon shadow-glow-neon' :
                'border-alert/50 bg-alert/12 text-alert'}`
                }>
                
                {approved ?
                <CheckIcon className="h-3.5 w-3.5" strokeWidth={2.6} /> :

                <CornerUpLeftIcon className="h-3.5 w-3.5" strokeWidth={2.4} />
                }
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-mist/80">
                    iteration {step.iteration}
                  </span>
                  <span className={`font-mono text-[11px] tracking-[0.12em] ${accent}`}>
                    {step.decision}
                  </span>
                  <span className="font-mono text-[10px] tabular-nums text-mist/80">
                    {step.at}
                  </span>
                  <span className="ml-auto font-mono text-[11px] tabular-nums text-slate-200">
                    {step.score}/100
                  </span>
                </div>

                <p className="mt-1.5 text-[12px] leading-relaxed text-slate-300">{step.reason}</p>

                {!approved &&
                <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-hull-400/55 bg-hull-700/60 px-2 py-1 font-mono text-[10px] text-mist/80">
                    returned to
                    <span className="text-amber">{AGENT_LABELS[step.to]}</span>
                  </div>
                }
              </div>
            </motion.li>);

        })}
      </ol>
    </section>);

}
