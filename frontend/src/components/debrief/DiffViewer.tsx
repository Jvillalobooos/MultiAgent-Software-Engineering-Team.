import React, { useId, useState } from 'react';
import { motion } from 'framer-motion';
import { FileCode2Icon, FileTextIcon } from 'lucide-react';
import { ApplyResult, ChangedFile, DiffLine, RunPhase } from '../../types/mission';

interface DiffViewerProps {
  files: ChangedFile[];
  workspaceChanged: boolean;
  sourceApplied: boolean;
  applyResult?: ApplyResult | null;
  phase?: RunPhase;
}

const KEYWORDS = [
'from',
'import',
'class',
'def',
'return',
'raise',
'if',
'not',
'or',
'and',
'in',
'for',
'with',
'None',
'True',
'False',
'self',
'float',
'str',
'list',
'set',
'int'];


const TOKEN_RE = /("""[\s\S]*?"""|"[^"]*"|'[^']*'|#.*$|@[\w.]+|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b)/g;

function highlight(text: string, language: ChangedFile['language']): React.ReactNode {
  if (!text) return '\u00A0';
  if (language === 'markdown') {
    if (text.trimStart().startsWith('#')) return <span className="text-electric">{text}</span>;
    return (
      <>
        {text.split(/(`[^`]*`)/g).map((part, i) =>
        part.startsWith('`') ?
        <span key={i} className="text-plasma">
              {part}
            </span> :

        <span key={i}>{part}</span>

        )}
      </>);

  }
  const parts = text.split(TOKEN_RE);
  return (
    <>
      {parts.map((part, i) => {
        if (!part) return null;
        if (part.startsWith('#')) {
          return (
            <span key={i} className="text-mist/80">
              {part}
            </span>);

        }
        if (/^("""|"|')/.test(part)) {
          return (
            <span key={i} className="text-amber/90">
              {part}
            </span>);

        }
        if (part.startsWith('@')) {
          return (
            <span key={i} className="text-plasma">
              {part}
            </span>);

        }
        if (/^\d/.test(part)) {
          return (
            <span key={i} className="text-neon/90">
              {part}
            </span>);

        }
        if (KEYWORDS.includes(part)) {
          return (
            <span key={i} className="text-electric">
              {part}
            </span>);

        }
        return <span key={i}>{part}</span>;
      })}
    </>);

}

const LINE_STYLE: Record<DiffLine['type'], string> = {
  add: 'bg-neon/[0.09]',
  del: 'bg-alert/[0.09]',
  ctx: '',
  meta: 'bg-hull-600/45 text-plasma'
};

const SIGN: Record<DiffLine['type'], string> = { add: '+', del: '-', ctx: ' ', meta: '@' };

export function DiffViewer({ files, workspaceChanged, sourceApplied, applyResult, phase }: DiffViewerProps) {
  const tabId = useId();
  const [activePath, setActivePath] = useState(files[0]?.path ?? '');
  const file = files.find((f) => f.path === activePath) ?? files[0];
  const lines = Array.isArray(file?.lines) ? file.lines : [];
  // source_applied marks a successful, verified apply, not every source write.
  // In particular, failed verification retains writes until the user restores.
  const provenance = phase === 'applying' ? 'Applying to project…'
    : applyResult?.status === 'restored' ? 'Restored from backup'
    : applyResult?.status === 'apply_failed'
      ? applyResult.test_exit_code !== null && applyResult.written_paths.length > 0
        ? 'Verification failed · project changes retained' : 'Apply failed · check project state'
    : applyResult?.status === 'conflict' ? 'Apply/restore conflict · review project state'
    : sourceApplied ? 'Applied to project'
    : workspaceChanged ? 'Workspace only · project unchanged'
    : 'Proposed · no files written';
  const provenanceClass = applyResult?.status === 'apply_failed' ? 'border-alert/40 bg-alert/10 text-alert'
    : sourceApplied || applyResult?.status === 'restored' ? 'border-neon/40 bg-neon/10 text-neon'
    : 'border-amber/40 bg-amber/10 text-amber';

  return (
    <section className="glass flex min-h-0 flex-col rounded-2xl shadow-panel" aria-label="Code diff">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hull-400/35 px-4 py-3">
        <h3 className="text-sm font-semibold tracking-tight text-slate-100">Code changes</h3>
        <span
          title={
            sourceApplied ? 'These changes are in your project on disk.' :
            'These changes exist only in this run\u2019s isolated copy. Your project is unchanged.'}
          className={`rounded border px-2 py-1 text-xs ${provenanceClass}`}>
          {provenance}
        </span>
      </div>

      {files.length === 0 ?
      <p className="px-4 py-8 text-center font-mono text-[11px] text-mist/80">
          This run proposed no file changes.
        </p> :
      <>
      <div
        role="tablist"
        aria-label="Changed files"
        className="thin-scroll flex gap-1 overflow-x-auto border-b border-hull-400/35 px-3 py-2">
        
        {files.map((f) => {
          const active = f.path === file?.path;
          const Icon = f.language === 'markdown' ? FileTextIcon : FileCode2Icon;
          return (
            <button
              key={f.path}
              role="tab"
              id={`${tabId}-tab-${f.path}`}
              aria-selected={active}
              aria-controls={`${tabId}-panel`}
              onClick={() => setActivePath(f.path)}
              className={`relative flex shrink-0 items-center gap-2 rounded-md px-3 py-2 font-mono text-[11px] transition-colors duration-200 ease-command ${
              active ?
              'bg-electric/10 text-slate-100' :
              'text-mist hover:bg-hull-600/50 hover:text-slate-200'}`
              }>
              
              <Icon className={`h-3.5 w-3.5 ${active ? 'text-electric' : 'text-mist/80'}`} />
              {f.path}
              <span className="text-neon/90" aria-label={`${f.additions} added`}>+{f.additions}</span>
              <span className="text-alert/90" aria-label={`${f.deletions} removed`}>-{f.deletions}</span>
              {active &&
              <motion.span
                layoutId="diff-tab"
                className="absolute inset-x-2 -bottom-[9px] h-[2px] rounded-full bg-electric"
                transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }} />

              }
            </button>);

        })}
      </div>

      <div
        id={`${tabId}-panel`}
        role="tabpanel"
        aria-labelledby={file ? `${tabId}-tab-${file.path}` : undefined}
        tabIndex={0}
        className="thin-scroll min-h-0 flex-1 overflow-auto py-2 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-electric">
        <table className="w-full border-collapse font-mono text-[11px] leading-[1.65]">
          <tbody>
            {lines.map((line, i) =>
            <tr key={i} className={LINE_STYLE[line.type]}>
                <td className="w-12 select-none pl-3 pr-1 text-right align-top text-mist/80 tabular-nums">
                  {line.oldNo ?? ''}
                </td>
                <td className="w-12 select-none pr-2 text-right align-top text-mist/80 tabular-nums">
                  {line.newNo ?? ''}
                </td>
                <td
                className={`w-4 select-none border-l border-hull-400/30 pl-2 pr-1 align-top ${
                line.type === 'add' ?
                'text-neon' :
                line.type === 'del' ?
                'text-alert' :
                'text-mist/80'}`
                }>
                
                  {SIGN[line.type]}
                </td>
                <td
                className={`whitespace-pre-wrap break-words pr-4 align-top ${
                line.type === 'meta' ? 'text-plasma' : 'text-slate-300'}`
                }>
                
                  {line.type === 'meta' ? line.text : highlight(line.text, file?.language ?? 'python')}
                </td>
              </tr>
            )}
            {lines.length === 0 &&
            <tr>
                <td colSpan={4} className="px-4 py-6 text-center">
                  <p className="text-[12px] text-slate-300">
                    No changes were recorded for{' '}
                    <span className="font-mono text-mist">{file?.path}</span>.
                  </p>
                  <p className="mt-1 text-[11px] text-mist">
                    No text hunks were recorded for this target.
                  </p>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      </>
      }
    </section>);

}
