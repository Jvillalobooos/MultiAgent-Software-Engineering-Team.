import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { LoaderCircleIcon } from 'lucide-react';
import { FinalReport, LaunchConfig } from '../../types/mission';
import { MAX_ITERATIONS } from '../../data/scenario';
import { useRunSimulation } from '../../hooks/useRunSimulation';
import { TopBar } from './TopBar';
import { AgentGraph } from './AgentGraph';
import { ActionTicker } from './ActionTicker';

interface MissionControlProps {
  config: LaunchConfig;
  speed: number;
  onFinish: (elapsed: number, report: FinalReport, runId: string) => void;
}

const ease = [0.23, 1, 0.32, 1] as const;

export function MissionControl({ config, speed, onFinish }: MissionControlProps) {
  const [handingOff, setHandingOff] = useState(false);
  const elapsedRef = useRef(0);
  const timerRef = useRef<number | null>(null);

  const handleComplete = useCallback((report: FinalReport, runId: string) => {
    setHandingOff(true);
    timerRef.current = window.setTimeout(() => onFinish(elapsedRef.current, report, runId), 1200);
  }, [onFinish]);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  const run = useRunSimulation({ config, speed, onComplete: handleComplete });
  elapsedRef.current = run.elapsed;

  return (
    <div className="circuit-grid flex h-screen w-full flex-col overflow-hidden">
      <TopBar
        runId={run.runId}
        elapsed={run.elapsed}
        iteration={run.iteration}
        maxIterations={MAX_ITERATIONS}
        status={run.status}
        projectPath={config.projectPath}
        writeMode={config.writeMode} />
      

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main className="relative flex min-h-0 flex-1 flex-col">
          <div className="flex items-baseline justify-between px-6 pt-5">
            <div>
              <h2 className="text-sm font-semibold tracking-tight text-slate-100">Live agent graph</h2>
              <p className="mt-0.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-mist/55">
                6 agents · 1 human gate · max {MAX_ITERATIONS} iterations
              </p>
            </div>
            <p className="hidden max-w-[340px] truncate font-mono text-[11px] text-electric/70 md:block">
              {run.caption}
            </p>
          </div>

          <div className="relative min-h-0 flex-1 px-4 pb-4 pt-2">
            <AgentGraph
              activeAgent={run.activeAgent}
              caption={run.caption}
              providers={run.providers}
              fallbacks={run.fallbacks}
              activeEdge={run.activeEdge}
              visitedEdges={run.visitedEdges}
              dimmed={handingOff} />
            

            <AnimatePresence>
              {handingOff &&
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3, ease }}
                className="absolute inset-0 z-10 flex items-center justify-center">
                
                  <div className="glass flex items-center gap-3 rounded-xl px-5 py-3.5 shadow-glow-neon">
                    <LoaderCircleIcon className="h-4 w-4 animate-spin text-neon" />
                    <span className="font-mono text-[12px] uppercase tracking-[0.18em] text-neon">
                      compiling mission debrief
                    </span>
                  </div>
                </motion.div>
              }
            </AnimatePresence>
          </div>
        </main>

        <div className="min-h-0 flex-1 lg:h-auto lg:flex-none">
          <ActionTicker events={run.events} />
        </div>
      </div>
    </div>);

}
