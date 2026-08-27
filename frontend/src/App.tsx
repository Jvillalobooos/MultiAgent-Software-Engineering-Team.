import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { FinalReport, LaunchConfig } from './types/mission';
import { LaunchScreen } from './components/launch/LaunchScreen';
import { MissionControl } from './components/mission/MissionControl';
import { MissionDebrief } from './components/debrief/MissionDebrief';

type Screen = 'launch' | 'mission' | 'debrief';

interface AppProps {
  /** Which screen to open on — handy for reviewing the debrief without waiting out the run. */
  initialScreen?: 'launch' | 'mission' | 'debrief';
  /** Pace of the simulated run. */
  runSpeed?: 'realtime' | 'fast';
}

const DEFAULT_CONFIG: LaunchConfig = {
  projectPath: 'sample_app',
  specification: 'Return only the latest five transactions belonging to the authorized user.',
  testSpecification: 'Verify the five-item limit and reject cross-user access with pytest.',
  writeMode: 'dry_run'
};

export function App({ initialScreen = 'launch', runSpeed = 'realtime' }: AppProps) {
  const [screen, setScreen] = useState<Screen>(initialScreen);
  const [config, setConfig] = useState<LaunchConfig>(DEFAULT_CONFIG);
  const [runKey, setRunKey] = useState(0);
  const [elapsed, setElapsed] = useState(38200);
  const [report, setReport] = useState<FinalReport | null>(null);
  const [runId, setRunId] = useState('');

  const startRun = (next: LaunchConfig) => {
    setConfig(next);
    setRunKey((k) => k + 1);
    setScreen('mission');
  };

  const replay = () => {
    setRunKey((k) => k + 1);
    setScreen('mission');
  };

  return (
    <div className="min-h-screen w-full bg-void">
      <AnimatePresence mode="wait">
        {screen === 'launch' &&
        <motion.div
          key="launch"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}>
          
            <LaunchScreen onLaunch={startRun} />
          </motion.div>
        }

        {screen === 'mission' &&
        <motion.div
          key={`mission-${runKey}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}>
          
            <MissionControl
            config={config}
            speed={runSpeed === 'fast' ? 2.5 : 1}
            onFinish={(ms, finalReport, completedRunId) => {
              setElapsed(ms);
              setReport(finalReport);
              setRunId(completedRunId);
              setScreen('debrief');
            }} />
          
          </motion.div>
        }

        {screen === 'debrief' && report &&
        <MissionDebrief
          key="debrief"
          report={report}
          config={config}
          elapsed={elapsed}
          runId={runId}
          onReplay={replay}
          onNewRun={() => setScreen('launch')} />

        }
      </AnimatePresence>
    </div>);

}
