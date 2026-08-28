import { Fragment } from 'react';
import { ChevronRightIcon, CornerUpLeftIcon } from 'lucide-react';
import { RouteHop } from '../../hooks/useRunGraph';
import { AGENT_LABELS } from '../../utils/format';

interface RouteTraceProps {
  route: RouteHop[];
}

/** The path the run actually walked, in order, with each remediation loop marked
 *  where it starts. Reading left to right tells you how the run got where it is —
 *  which the graph alone cannot show once an edge has been traversed twice. */
export function RouteTrace({ route }: RouteTraceProps) {
  if (route.length === 0) return null;

  const currentIndex = route.length - 1;

  return (
    <div
      aria-label="Route taken"
      className="thin-scroll flex items-center gap-1.5 overflow-x-auto rounded-xl border border-hull-400/35 bg-hull-800/40 px-3 py-2.5">

      <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.18em] text-mist/80">
        route
      </span>

      {route.map((hop, index) => {
        const isCurrent = index === currentIndex;
        const isReject = hop.kind === 'reject';
        const isBranch = hop.kind === 'branch';
        const opensIteration = index > 0 && hop.iteration !== route[index - 1].iteration;

        return (
          <Fragment key={`${hop.agent}-${index}`}>
            {index > 0 && (
              isReject ?
              <CornerUpLeftIcon
                aria-label="remediation loop"
                className="h-3 w-3 shrink-0 text-amber/80" /> :

              <ChevronRightIcon
                aria-hidden="true"
                className={`h-3 w-3 shrink-0 ${isBranch ? 'text-amber/60' : 'text-electric/45'}`} />
            )}

            {opensIteration &&
            <span className="shrink-0 rounded border border-amber/40 bg-amber/10 px-1.5 py-[1px] font-mono text-[10px] uppercase tracking-[0.12em] text-amber">
                iter {hop.iteration}
              </span>
            }

            <span
              aria-current={isCurrent ? 'step' : undefined}
              className={`shrink-0 rounded border px-2 py-[3px] font-mono text-[10px] transition-colors duration-300 ease-command ${
              isCurrent ?
              'border-electric/50 bg-electric/10 text-electric' :
              'border-hull-400/45 bg-hull-900/40 text-slate-300/75'}`
              }>

              {AGENT_LABELS[hop.agent]}
            </span>
          </Fragment>);

      })}
    </div>);

}
