import { useEffect, useState } from 'react';
import { RunClient } from '../../api/runClient';
import { ProjectRef } from '../../types/mission';
import { ProjectHeader } from './ProjectHeader';
import { ChatComposer, RunSubmission } from './ChatComposer';
import { RunCard } from './RunCard';

interface ChatWorkspaceProps {
  client: RunClient;
}

/** Owns the selected project and the ordered list of run identifiers for this
 *  session. Each submitted message starts exactly one independent run — never
 *  a continuation of a prior message's context. */
export function ChatWorkspace({ client }: ChatWorkspaceProps) {
  const [selectedProject, setSelectedProject] = useState<ProjectRef | null>(null);
  const [runIds, setRunIds] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    client.listRuns()
      .then((summaries) => {
        if (cancelled) return;
        setRunIds(summaries.map((summary) => summary.run_id));
      })
      .catch(() => {
        // No history available (fresh backend, or offline) — start with an empty session.
      });
    return () => { cancelled = true; };
  }, [client]);

  const handleSubmit = async ({ message, testSpec, authorizeWrites }: RunSubmission) => {
    if (!selectedProject) return;
    const runId = await client.createRun(selectedProject.path, message, { testSpec, authorizeWrites });
    setRunIds((current) => [...current, runId]);
  };

  return (
    <div className="flex min-h-screen w-full flex-col">
      <ProjectHeader client={client} selectedProject={selectedProject} onProjectSelected={setSelectedProject} />

      <div className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col gap-5 px-4 py-6 md:px-8">
        {runIds.length === 0 ?
        <p className="mt-10 text-center font-mono text-[12px] text-mist/45">
            Select a project folder, then describe a change to start your first run.
          </p> :

        runIds.map((runId, index) => <RunCard key={runId} runId={runId} client={client} index={index + 1} />)
        }
      </div>

      <ChatComposer disabled={!selectedProject} projectPath={selectedProject?.path ?? null} onSubmit={handleSubmit} />
    </div>);

}
