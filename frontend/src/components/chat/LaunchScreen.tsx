import {
  ClipboardListIcon,
  CodeXmlIcon,
  FlaskConicalIcon,
  GaugeIcon,
  LayersIcon,
  ShieldCheckIcon } from
'lucide-react';
import { BrandMark } from '../brand/BrandMark';

interface LaunchScreenProps {
  hasProject: boolean;
}

const PIPELINE = [
{ label: 'Product', role: 'Requirements', icon: ClipboardListIcon },
{ label: 'Architecture', role: 'System design', icon: LayersIcon },
{ label: 'Developer', role: 'Implementation', icon: CodeXmlIcon },
{ label: 'Security', role: 'Static + SCA', icon: ShieldCheckIcon },
{ label: 'Testing', role: 'Suite execution', icon: FlaskConicalIcon },
{ label: 'Reviewer', role: 'Verdict + score', icon: GaugeIcon }];


/** The screen the app always opens on: what the system is, what it will do, and —
 *  via the history beside it — what it has already done. It deliberately renders no
 *  run, so a restart never replays past executions into the viewport. */
export function LaunchScreen({ hasProject }: LaunchScreenProps) {
  return (
    <section aria-label="Start a run" className="glass rounded-2xl p-6 shadow-panel">
      <div className="flex items-center gap-2.5">
        <BrandMark className="h-6 w-6" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-50">
          Autonomous engineering team
        </h2>
      </div>
      <p className="mt-2 max-w-[62ch] text-[13px] leading-relaxed text-mist">
        {hasProject ?
        'Describe a change below. Six agents plan, implement, scan, test and review it in an isolated copy of your project — nothing is written back until you approve it.' :
        'Select a project folder to begin. Six agents will plan, implement, scan, test and review your change in an isolated copy — nothing is written back until you approve it.'}
      </p>

      <ol className="mt-5 flex flex-wrap gap-2" aria-label="Agent pipeline">
        {PIPELINE.map(({ label, role, icon: Icon }, index) =>
        <li
          key={label}
          className="glass-soft flex min-w-[132px] flex-1 items-center gap-2.5 rounded-lg px-3 py-2.5">

            <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-electric/80" />
            <div className="min-w-0">
              <p className="truncate text-[12px] font-medium text-slate-100">{label}</p>
              <p className="truncate font-mono text-[10px] uppercase tracking-[0.1em] text-mist/80">
                {role}
              </p>
            </div>
            <span className="ml-auto font-mono text-[10px] text-mist/80">{index + 1}</span>
          </li>
        )}
      </ol>
    </section>);

}
