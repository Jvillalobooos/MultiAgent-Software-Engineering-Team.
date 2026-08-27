import { useEffect, useState } from 'react';
import { FolderOpenIcon, HexagonIcon } from 'lucide-react';
import { RunClient } from '../../api/runClient';
import { ProjectRef } from '../../types/mission';

interface ProjectHeaderProps {
  client: RunClient;
  selectedProject: ProjectRef | null;
  onProjectSelected: (project: ProjectRef) => void;
}

type Health = 'checking' | 'online' | 'offline';

/** Persistent chat-shell header: canonical selected project, backend health, and the
 *  native folder picker — the only way a project is chosen (no manual path entry). */
export function ProjectHeader({ client, selectedProject, onProjectSelected }: ProjectHeaderProps) {
  const [health, setHealth] = useState<Health>('checking');
  const [picking, setPicking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    client.listRuns()
      .then(() => { if (!cancelled) setHealth('online'); })
      .catch(() => { if (!cancelled) setHealth('offline'); });
    return () => { cancelled = true; };
  }, [client]);

  const handlePick = async () => {
    setPicking(true);
    try {
      const result = await client.pickProject();
      if (result.status === 'selected' && result.project) {
        onProjectSelected(result.project);
      }
      // 'cancelled' leaves the currently selected project (if any) unchanged.
    } finally {
      setPicking(false);
    }
  };

  return (
    <header className="glass sticky top-0 z-10 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-b-2xl px-5 py-4 shadow-panel">
      <div className="flex items-center gap-2.5">
        <HexagonIcon className="h-4 w-4 text-electric" strokeWidth={2.2} />
        <span className="text-sm font-semibold tracking-tight text-slate-50">Multiagent Chat</span>
      </div>

      <div className="min-w-0 flex-1 font-mono text-[11px] text-mist/70">
        {selectedProject ?
        <span className="truncate" title={selectedProject.path}>
            {selectedProject.name} · {selectedProject.path}
          </span> :

        <span className="text-mist/45">No project selected</span>
        }
      </div>

      <span
        role="status"
        aria-label="Backend health"
        className={`rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] ${
        health === 'online' ?
        'border-neon/45 bg-neon/10 text-neon' :
        health === 'offline' ?
        'border-alert/45 bg-alert/10 text-alert' :
        'border-hull-400/55 text-mist/55'}`
        }>

        {health === 'checking' ? 'checking…' : health}
      </span>

      <button
        type="button"
        onClick={handlePick}
        disabled={picking}
        className="flex items-center gap-2 rounded-md border border-electric/50 bg-electric/15 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-slate-50 transition-colors duration-200 ease-command hover:bg-electric/25 disabled:opacity-50">

        <FolderOpenIcon className="h-3.5 w-3.5 text-electric" />
        Select folder
      </button>
    </header>);

}
