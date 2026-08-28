import { FormEvent, KeyboardEvent, useEffect, useId, useRef, useState } from 'react';
import { SendIcon } from 'lucide-react';

export interface RunSubmission {
  message: string;
  testSpec: string;
  authorizeWrites: boolean;
}

/** A past instruction loaded back into the composer. `token` changes on every reuse so
 *  loading the same instruction twice still refills the fields. */
export interface ComposerPrefill {
  message: string;
  testSpec: string;
  token: number;
}

interface ChatComposerProps {
  disabled: boolean;
  projectPath: string | null;
  prefill?: ComposerPrefill | null;
  onSubmit: (submission: RunSubmission) => Promise<void>;
}

/** Each submission is independent. Write permission is explicit and never carried
 *  over to another project or submission. */
export function ChatComposer({ disabled, projectPath, prefill, onSubmit }: ChatComposerProps) {
  const id = useId();
  const taskField = useRef<HTMLTextAreaElement>(null);
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

  useEffect(() => {
    if (!prefill) return;
    setValue(prefill.message);
    setTestSpec(prefill.testSpec);
    setError(null);
    // Write permission is never inherited from a previous run.
    setAuthorizeWrites(false);
    taskField.current?.focus();
  }, [prefill]);

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
  const fieldClass = 'thin-scroll min-h-[56px] w-full resize-y rounded-lg border border-hull-400 bg-hull-800 px-3 py-1.5 text-sm leading-relaxed text-slate-100 outline-none placeholder:text-mist focus:border-electric focus:ring-1 focus:ring-electric disabled:opacity-50';

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="New run"
      aria-busy={submitting}
      className="sticky bottom-0 z-10 border-t border-hull-400 bg-hull-900 px-4 py-2.5 pb-[calc(env(safe-area-inset-bottom,0px)+0.625rem)]">
      <div className="mx-auto flex w-full max-w-[1136px] flex-col gap-2">
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label htmlFor={`${id}-task`} className="mb-1 flex items-baseline gap-2 text-[13px] font-medium text-slate-100">
              Task <span className="font-mono text-xs font-normal text-mist">--spec</span>
            </label>
            <textarea
              ref={taskField}
              id={`${id}-task`}
              aria-label="Task"
              value={value}
              disabled={isDisabled}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={handleShortcut}
              placeholder={disabled ? 'Select a project folder to start…' : 'Describe the change you want…'}
              rows={2}
              className={fieldClass} />
          </div>
          <div>
            <label htmlFor={`${id}-tests`} className="mb-1 flex flex-wrap items-baseline gap-2 text-[13px] font-medium text-slate-100">
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
              rows={2}
              className={fieldClass} />
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-2">
          <fieldset disabled={isDisabled} className="min-w-0 flex-1">
            <legend className="sr-only">Execution mode</legend>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <label className="flex min-h-11 cursor-pointer items-center gap-2 text-[13px] text-slate-100 md:min-h-[36px]">
                <input type="radio" name={`${id}-mode`} checked={!authorizeWrites} onChange={() => setAuthorizeWrites(false)} className="h-4 w-4 accent-electric focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric" />
                Dry run <span className="font-mono text-[11px] text-mist">--dry-run</span>
              </label>
              <label className="flex min-h-11 cursor-pointer items-center gap-2 text-[13px] text-slate-100 md:min-h-[36px]">
                <input type="radio" name={`${id}-mode`} checked={authorizeWrites} onChange={() => setAuthorizeWrites(true)} className="h-4 w-4 accent-electric focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric" />
                Authorize writes <span className="font-mono text-[11px] text-mist">--authorize-writes</span>
              </label>
              <p role="note" className={`min-w-0 flex-1 truncate text-[11px] ${authorizeWrites ? 'text-amber' : 'text-mist'}`}>
                {authorizeWrites ? <>Writes to <span className="font-mono">{projectPath}</span>.</> : 'Dry run proposes changes without writing project files.'}
              </p>
            </div>
          </fieldset>
          <div className="flex shrink-0 items-center gap-3">
            <span className="hidden text-[11px] text-mist sm:inline">Ctrl / ⌘ + Enter</span>
            <button
              type="submit"
              disabled={isDisabled || !value.trim()}
              className="flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-md border border-electric/50 bg-electric/15 px-4 py-1.5 text-[13px] font-medium text-slate-50 md:min-h-[40px] transition-colors hover:bg-electric/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric disabled:cursor-not-allowed disabled:opacity-40">
              <SendIcon aria-hidden="true" className="h-4 w-4 text-electric" />
              {submitting ? 'Starting…' : authorizeWrites ? 'Execute with writes' : 'Execute dry run'}
            </button>
          </div>
        </div>
        {error && <p role="alert" className="rounded-md border border-alert/40 bg-alert/10 px-3 py-2 text-sm text-alert">{error}</p>}
      </div>
    </form>
  );
}
