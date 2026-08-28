import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeftIcon } from 'lucide-react';
import { RunClient } from '../../api/runClient';
import { ProjectRef, RunSummary } from '../../types/mission';
import { ProjectHeader } from './ProjectHeader';
import { ChatComposer, ComposerPrefill, RunSubmission } from './ChatComposer';
import { RunCard } from './RunCard';
import { RunHistory } from './RunHistory';
import { LaunchScreen } from './LaunchScreen';

interface ChatWorkspaceProps {
  client: RunClient;
}

/** Merge server truth over locally-known runs, keeping any run this session started
 *  that the backend has not listed back yet. Server order (newest first) is preserved. */
function mergeSummaries(local: RunSummary[], remote: RunSummary[]): RunSummary[] {
  const remoteIds = new Set(remote.map((summary) => summary.run_id));
  return [...remote, ...local.filter((summary) => !remoteIds.has(summary.run_id))];
}

/** Owns the selected project, the run-history index, and which single run is open.
 *  Each submitted message starts exactly one independent run — never a continuation
 *  of a prior message's context — and exactly one run is ever mounted at a time, so
 *  past runs are navigable history rather than a stack of live cards. */
export function ChatWorkspace({ client }: ChatWorkspaceProps) {
  const [selectedProject, setSelectedProject] = useState<ProjectRef | null>(null);
  const [summaries, setSummaries] = useState<RunSummary[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<ComposerPrefill | null>(null);
  const filterRef = useRef<HTMLInputElement>(null);

  const loadHistory = useCallback(async () => {
    try {
      const remote = await client.listRuns();
      setSummaries((current) => mergeSummaries(current, remote));
    } catch {
      // No history available (fresh backend, or offline) — keep what this session knows.
    }
  }, [client]);

  // The app always opens on the launch screen: history is indexed, never mounted.
  useEffect(() => {void loadHistory();}, [loadHistory]);

  const handleSubmit = async ({ message, testSpec, authorizeWrites }: RunSubmission) => {
    if (!selectedProject) return;
    const runId = await client.createRun(selectedProject.path, message, { testSpec, authorizeWrites });
    const now = new Date().toISOString();
    // Recorded locally so the new run appears in history immediately; the next
    // history load replaces it with the backend's authoritative summary.
    setSummaries((current) => mergeSummaries(current, [{
      run_id: runId,
      project_path: selectedProject.path,
      message,
      test_spec: testSpec || null,
      authorize_writes: authorizeWrites,
      phase: 'queued',
      created_at: now,
      updated_at: now
    }]));
    setActiveRunId(runId);
  };

  const handleBackToHistory = useCallback(() => {
    setActiveRunId(null);
    void loadHistory();
  }, [loadHistory]);

  /** Reusing a past instruction refills the composer; it never launches a run, because
   *  launching spends provider quota against a real project. */
  const handleReuse = useCallback((summary: RunSummary) => {
    setPrefill({ message: summary.message, testSpec: summary.test_spec ?? '', token: Date.now() });
    setActiveRunId(null);
  }, []);

  // Escape leaves an open run; "/" jumps to the history filter. Both stay out of the
  // way while the user is typing into a field.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target instanceof HTMLElement &&
        (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
      if (event.key === 'Escape' && !typing && activeRunId !== null) {
        event.preventDefault();
        handleBackToHistory();
        return;
      }
      if (event.key === '/' && !typing && activeRunId === null) {
        event.preventDefault();
        filterRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeRunId, handleBackToHistory]);

  return (
    <div className="flex min-h-screen w-full flex-col">
      <ProjectHeader client={client} selectedProject={selectedProject} onProjectSelected={setSelectedProject} />

      <div className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col gap-5 px-4 py-6 md:px-8">
        {activeRunId === null ?
        <div className="flex flex-col gap-5">
            <LaunchScreen hasProject={selectedProject !== null} />
            <RunHistory
              ref={filterRef}
              summaries={summaries}
              activeRunId={activeRunId}
              onOpenRun={setActiveRunId}
              onReuse={handleReuse} />
          </div> :

        <div className="flex flex-col gap-4">
            <button
            type="button"
            onClick={handleBackToHistory}
            className="flex w-fit items-center gap-2 rounded-md border border-hull-400/55 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-mist/80 transition-colors hover:border-electric/45 hover:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric">

              <ArrowLeftIcon aria-hidden="true" className="h-3.5 w-3.5" />
              Back to history
              <kbd className="ml-1 rounded border border-hull-400/55 px-1.5 py-0.5 text-[10px] normal-case tracking-normal">esc</kbd>
            </button>
            <RunCard key={activeRunId} runId={activeRunId} client={client} />
          </div>
        }
      </div>

      <ChatComposer
        disabled={!selectedProject}
        projectPath={selectedProject?.path ?? null}
        prefill={prefill}
        onSubmit={handleSubmit} />
    </div>);

}
