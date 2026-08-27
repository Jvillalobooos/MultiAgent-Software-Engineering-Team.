import { FormEvent, useState } from 'react';
import { SendIcon } from 'lucide-react';

interface ChatComposerProps {
  disabled: boolean;
  onSubmit: (message: string) => Promise<void>;
}

/** One message == one independent run. Never accumulates prior messages: each
 *  submission is a fresh string handed to the caller, with no local history. */
export function ChatComposer({ disabled, onSubmit }: ChatComposerProps) {
  const [value, setValue] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled || submitting) return;

    setSubmitting(true);
    try {
      await onSubmit(trimmed);
      setValue(''); // clear only on success
    } catch {
      // restore (i.e. leave) the message on failure — nothing to do, we never cleared it.
    } finally {
      setSubmitting(false);
    }
  };

  const isDisabled = disabled || submitting;

  return (
    <form
      onSubmit={handleSubmit}
      className="glass sticky bottom-0 z-10 flex items-end gap-3 rounded-t-2xl px-4 py-3 pb-[calc(env(safe-area-inset-bottom,0px)+0.75rem)] shadow-panel">

      <textarea
        aria-label="Task"
        value={value}
        disabled={isDisabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            void handleSubmit(event);
          }
        }}
        placeholder={disabled ? 'Select a project folder to start…' : 'Describe the change you want…'}
        rows={2}
        className="thin-scroll min-h-[44px] flex-1 resize-none rounded-lg border border-hull-400/45 bg-hull-800/60 px-3 py-2 font-mono text-[12.5px] text-slate-100 outline-none placeholder:text-mist/40 focus:border-electric/50 disabled:opacity-50" />

      <button
        type="submit"
        disabled={isDisabled || !value.trim()}
        className="flex shrink-0 items-center gap-2 rounded-md border border-electric/50 bg-electric/15 px-4 py-2.5 font-mono text-[11px] uppercase tracking-[0.14em] text-slate-50 transition-colors duration-200 ease-command hover:bg-electric/25 disabled:opacity-40">

        <SendIcon className="h-3.5 w-3.5 text-electric" />
        Execute
      </button>
    </form>);

}
