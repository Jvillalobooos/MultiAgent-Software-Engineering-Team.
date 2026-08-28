import { FormEvent, useEffect, useId, useRef, useState } from 'react';
import { FolderOpenIcon } from 'lucide-react';
import { BrandMark } from '../brand/BrandMark';
import { RunClient } from '../../api/runClient';
import { ProjectRef } from '../../types/mission';

interface ProjectHeaderProps {
  client: RunClient;
  selectedProject: ProjectRef | null;
  onProjectSelected: (project: ProjectRef) => void;
}

type Health = 'checking' | 'online' | 'offline';

/** Both selection routes use the backend's canonical, validated project path. */
export function ProjectHeader({ client, selectedProject, onProjectSelected }: ProjectHeaderProps) {
  const id = useId();
  const [health, setHealth] = useState<Health>('checking');
  const [picking, setPicking] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [path, setPath] = useState('');
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pathInput = useRef<HTMLInputElement>(null);
  const selectionSequence = useRef(0);

  useEffect(() => {
    if (manualOpen) pathInput.current?.focus();
  }, [manualOpen]);

  useEffect(() => {
    let cancelled = false;
    client.listRuns()
      .then(() => { if (!cancelled) setHealth('online'); })
      .catch(() => { if (!cancelled) setHealth('offline'); });
    return () => { cancelled = true; };
  }, [client]);

  const handlePick = async () => {
    const sequence = ++selectionSequence.current;
    setPicking(true);
    setError(null);
    try {
      const result = await client.pickProject();
      if (sequence === selectionSequence.current && result.status === 'selected' && result.project) {
        onProjectSelected(result.project);
        setPath(result.project.path);
        setManualOpen(false);
      }
    } catch (cause) {
      if (sequence === selectionSequence.current) {
        setError(cause instanceof Error ? cause.message : 'Could not open the folder picker. Enter the project path below.');
        setManualOpen(true);
      }
    } finally {
      setPicking(false);
    }
  };

  const handleManualSelection = async (event: FormEvent) => {
    event.preventDefault();
    if (!path.trim() || validating) return;
    const sequence = ++selectionSequence.current;
    setValidating(true);
    setError(null);
    try {
      const result = await client.selectProject(path.trim());
      if (sequence === selectionSequence.current && result.status === 'selected' && result.project) {
        onProjectSelected(result.project);
        setPath(result.project.path);
        setManualOpen(false);
      }
    } catch (cause) {
      if (sequence === selectionSequence.current) {
        setError(cause instanceof Error ? cause.message : 'Could not select this folder. Check the path and try again.');
      }
    } finally {
      setValidating(false);
    }
  };

  return (
    <header className="glass sticky top-0 z-10 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-b-2xl px-5 py-4 shadow-panel">
      <div className="flex items-center gap-2.5">
        <BrandMark className="h-6 w-6" />
        <h1 className="text-sm font-semibold tracking-tight text-slate-50">Multiagent Chat</h1>
      </div>

      <div className="min-w-0 flex-1 font-mono text-xs text-mist">
        {selectedProject ?
        <span className="block truncate" title={selectedProject.path}>
            {selectedProject.name} · {selectedProject.path}
          </span> :

        <span>No project selected</span>
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
        'border-hull-400/55 text-mist/80'}`
        }>

        {health === 'checking' ? 'checking…' : health}
      </span>

      <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={handlePick}
        aria-label="Select folder"
        aria-busy={picking}
        disabled={picking}
        className="flex min-h-11 items-center gap-2 rounded-md border border-electric/50 bg-electric/15 px-3 py-2 text-sm text-slate-50 transition-colors hover:bg-electric/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric disabled:opacity-50">

        <FolderOpenIcon aria-hidden="true" className="h-4 w-4 text-electric" />
        {picking ? 'Opening picker…' : 'Select folder'}
      </button>
      <button
        type="button"
        aria-expanded={manualOpen}
        aria-controls={`${id}-manual`}
        onClick={() => {
          setManualOpen((open) => !open);
          if (!manualOpen && selectedProject) setPath(selectedProject.path);
        }}
        className="min-h-11 rounded-md px-3 py-2 text-sm text-mist transition-colors hover:bg-hull-600 hover:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric">
        Enter path
      </button>
      </div>
      {manualOpen && (
        <form id={`${id}-manual`} onSubmit={handleManualSelection} className="flex w-full flex-wrap items-end gap-3 border-t border-hull-400/50 pt-3" aria-busy={validating}>
          <div className="min-w-[min(100%,16rem)] flex-1">
            <label htmlFor={`${id}-path`} className="mb-1.5 block text-sm text-slate-100">Project folder path</label>
            <input
              ref={pathInput}
              id={`${id}-path`}
              value={path}
              onChange={(event) => setPath(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              disabled={validating}
              placeholder="/Users/you/project or C:\\Users\\you\\project"
              className="min-h-11 w-full rounded-md border border-hull-400 bg-hull-800 px-3 py-2 font-mono text-sm text-slate-100 outline-none placeholder:text-mist focus:border-electric focus:ring-1 focus:ring-electric disabled:opacity-50" />
          </div>
          <button type="submit" disabled={validating || !path.trim()} className="min-h-11 rounded-md border border-electric/50 bg-electric/15 px-4 py-2 text-sm text-slate-100 hover:bg-electric/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric disabled:opacity-50">
            {validating ? 'Checking…' : 'Use folder'}
          </button>
          <p className="w-full text-xs text-mist">Use an existing folder on the computer running this app. macOS and Windows paths are supported.</p>
        </form>
      )}
      {error && <p role="alert" className="w-full rounded-md border border-alert/40 bg-alert/10 px-3 py-2 text-sm text-alert">{error}</p>}
    </header>);

}
