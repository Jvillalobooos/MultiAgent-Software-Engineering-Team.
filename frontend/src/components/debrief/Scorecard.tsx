import { motion } from 'framer-motion';
import { ReviewResult, SubscoreKey } from '../../types/mission';
import { SUBSCORE_LABELS } from '../../data/report';
import { STATUS_THEME } from '../../utils/format';

interface ScorecardProps {
  review: ReviewResult;
}

const ease = [0.23, 1, 0.32, 1] as const;

const colorFor = (score: number): string =>
score >= 90 ? '#49e08a' : score >= 80 ? '#3fb6ff' : score >= 70 ? '#ffb545' : '#ff5c6e';

function Gauge({ label, score, delay }: {label: string;score: number;delay: number;}) {
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const color = colorFor(score);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-[68px] w-[68px]">
        <svg viewBox="0 0 68 68" className="h-full w-full -rotate-90">
          <circle cx="34" cy="34" r={radius} fill="none" stroke="#18243c" strokeWidth="5" />
          <motion.circle
            cx="34"
            cy="34"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: circumference * (1 - score / 100) }}
            transition={{ duration: 0.9, delay, ease }}
            style={{ filter: `drop-shadow(0 0 6px ${color}66)` }} />
          
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3, delay: delay + 0.1, ease }}
            className="font-mono text-[14px] font-medium tabular-nums text-slate-100">
            
            {score}
          </motion.span>
        </div>
      </div>
      <span className="text-center text-[10px] leading-tight text-mist/80">{label}</span>
    </div>);

}

export function Scorecard({ review }: ScorecardProps) {
  const theme = STATUS_THEME[review.status];
  const keys = Object.keys(review.subscores) as SubscoreKey[];
  const totalCircumference = 2 * Math.PI * 46;

  return (
    <section className="glass rounded-2xl p-5 shadow-panel" aria-label="Reviewer scorecard">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold tracking-tight text-slate-100">Reviewer scorecard</h3>
          <p className="mt-0.5 text-[11px] text-mist">
            Six weighted subscores out of 100. Below the gate, the run loops back instead of approving.
          </p>
        </div>
        <span
          className={`rounded border px-2 py-0.5 font-mono text-[10px] tracking-[0.14em] ${theme.border} ${theme.bg} ${theme.text}`}>
          
          {theme.label}
        </span>
      </div>

      <div className="mt-5 flex flex-col items-center gap-6 sm:flex-row sm:items-center">
        <div className="relative h-[124px] w-[124px] shrink-0">
          <svg viewBox="0 0 108 108" className="h-full w-full -rotate-90">
            <circle cx="54" cy="54" r="46" fill="none" stroke="#18243c" strokeWidth="7" />
            <motion.circle
              cx="54"
              cy="54"
              r="46"
              fill="none"
              stroke={colorFor(review.score)}
              strokeWidth="7"
              strokeLinecap="round"
              strokeDasharray={totalCircumference}
              initial={{ strokeDashoffset: totalCircumference }}
              animate={{ strokeDashoffset: totalCircumference * (1 - review.score / 100) }}
              transition={{ duration: 1.1, ease }}
              style={{ filter: `drop-shadow(0 0 10px ${colorFor(review.score)}77)` }} />
            
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="font-mono text-[34px] font-medium leading-none tabular-nums text-slate-50">
              {review.score}
            </span>
            <span className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-mist/80">
              total / 100
            </span>
          </div>
        </div>

        <div className="grid flex-1 grid-cols-3 gap-x-2 gap-y-4">
          {keys.map((key, i) =>
          <Gauge
            key={key}
            label={SUBSCORE_LABELS[key]}
            score={review.subscores[key]}
            delay={0.15 + i * 0.09} />

          )}
        </div>
      </div>

      <p className="mt-5 border-t border-hull-400/35 pt-4 text-[12px] leading-relaxed text-mist">
        {review.reason}
      </p>

      {review.problems.length > 0 &&
      <ul className="mt-3 space-y-1.5">
          {review.problems.map((problem) =>
        <li key={problem} className="flex gap-2 font-mono text-[11px] leading-snug text-amber/85">
              <span aria-hidden="true" className="text-amber/80">▸</span>
              {problem}
            </li>
        )}
        </ul>
      }
    </section>);

}
