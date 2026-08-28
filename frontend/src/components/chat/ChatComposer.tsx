import { FormEvent, KeyboardEvent, useEffect, useId, useRef, useState } from 'react';
import { SendIcon } from 'lucide-react';

export interface RunSubmission {
  message: string;
  testSpec: string;
  authorizeWrites: boolean;
}

interface ChatComposerProps {
  disabled: boolean;
  projectPath: string | null;
  onSubmit: (submission: RunSubmission) => Promise<void>;
}

/** Each submission is independent. Write permission is explicit and never carried
 *  over to another project or submission. */
export function ChatComposer({ disabled, projectPath, onSubmit }: ChatComposerProps) {
  const id = useId();
  const [value, setValue] = useState('');
  const [testSpec, setTestSpec] = useState('');
  const [authorizeWrites, setAuthorizeWrites] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    setAuthorizeWrites(false);
    setError(null);
  }, [projectPath]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled || !projectPath || inFlight.current) return;

    inFlight.current = true;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ message: trimmed, testSpec: testSpec.trim(), authorizeWrites });
      setValue('');
      setTestSpec('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start the run. Your instructions are saved here.');
    } finally {
      inFlight.current = false;
      setSubmitting(false);
      setAuthorizeWrites(false);
    }
  };

  const handleShortcut = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void handleSubmit(event);
    }
  };

  const isDisabled = disabled || !projectPath || submitting;
  const fieldClass = 'thin-scroll min-h-[88px] w-full resize-y rounded-lg border border-hull-400 bg-hull-800 px-3 py-2 text-sm leading-relaxed text-slate-100 outline-none placeholder:text-mist focus:border-electric focus:ring-1 focus:ring-electric disabled:opacity-50';

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="New run"
      aria-busy={submitting}
      className="sticky bottom-0 z-10 border-t border-hull-400 bg-hull-900 px-4 py-4 pb-[calc(env(safe-area-inset-bottom,0px)+1rem)]">
      <div className="mx-auto flex w-full max-w-[1136px] flex-col gap-3">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label htmlFor={`${id}-task`} className="mb-1.5 flex items-baseline gap-2 text-sm font-medium text-slate-100">
              Task <span className="font-mono text-xs font-normal text-mist">--spec</span>
            </label>
            <textarea
              id={`${id}-task`}
              aria-label="Task"
              value={value}
              disabled={isDisabled}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={handleShortcut}
              placeholder={disabled ? 'Select a project folder to start…' : 'Describe the change you want…'}
              rows={3}
              className={fieldClass} />
          </div>
          <div>
            <label htmlFor={`${id}-tests`} className="mb-1.5 flex flex-wrap items-baseline gap-2 text-sm font-medium text-slate-100">
              Test specification <span className="font-mono text-xs font-normal text-mist">--test-spec · optional</span>
            </label>
            <textarea
              id={`${id}-tests`}
              aria-label="Test specification"
              value={testSpec}
              disabled={isDisabled}
              onChange={(event) => setTestSpec(event.target.value)}
              onKeyDown={handleShortcut}
              placeholder="Describe the tests and expected results…"
              rows={3}
              className={fieldClass} />
          </div>
        </div>
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <fieldset disabled={isDisabled} className="min-w-0 flex-1">
            <legend className="text-xs font-medium text-mist">Execution mode</legend>
            <div className="flex flex-wrap gap-x-5">
              <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm text-slate-100">
                <input type="radio" name={`${id}-mode`} checked={!authorizeWrites} onChange={() => setAuthorizeWrites(false)} className="h-4 w-4 accent-electric focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric" />
                Dry run <span className="font-mono text-xs text-mist">--dry-run</span>
              </label>
              <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm text-slate-100">
                <input type="radio" name={`${id}-mode`} checked={authorizeWrites} onChange={() => setAuthorizeWrites(true)} className="h-4 w-4 accent-electric focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric" />
                Authorize writes <span className="font-mono text-xs text-mist">--authorize-writes</span>
              </label>
            </div>
          </fieldset>
          <button
            type="submit"
            disabled={isDisabled || !value.trim()}
            className="flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-md border border-electric/50 bg-electric/15 px-4 py-2 text-sm font-medium text-slate-50 transition-colors hover:bg-electric/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric disabled:cursor-not-allowed disabled:opacity-40">
            <SendIcon aria-hidden="true" className="h-4 w-4 text-electric" />
            {submitting ? 'Starting…' : authorizeWrites ? 'Execute with writes' : 'Execute dry run'}
          </button>
        </div>
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 text-xs leading-relaxed">
          <p role="note" className={`min-w-0 flex-1 break-words ${authorizeWrites ? 'text-amber' : 'text-mist'}`}>
            {authorizeWrites ? <>Approved changes may be written to <span className="font-mono">{projectPath}</span>.</> : 'Dry run proposes changes without writing project files.'}
          </p>
          <span className="text-mist">Ctrl / ⌘ + Enter to execute</span>
        </div>
        {error && <p role="alert" className="rounded-md border border-alert/40 bg-alert/10 px-3 py-2 text-sm text-alert">{error}</p>}
      </div>
    </form>
  );
}
