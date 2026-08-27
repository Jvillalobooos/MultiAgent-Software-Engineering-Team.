import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { FileCode2Icon, FileTextIcon } from 'lucide-react';
import { ChangedFile, DiffLine } from '../../types/mission';

interface DiffViewerProps {
  files: ChangedFile[];
  applied: boolean;
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
            <span key={i} className="text-mist/50">
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
  add: 'bg-neon/[0.08] border-l-2 border-neon/60',
  del: 'bg-alert/[0.08] border-l-2 border-alert/60',
  ctx: 'border-l-2 border-transparent',
  meta: 'bg-hull-600/50 border-l-2 border-plasma/50 text-plasma'
};

const SIGN: Record<DiffLine['type'], string> = { add: '+', del: '-', ctx: ' ', meta: '@' };

export function DiffViewer({ files, applied }: DiffViewerProps) {
  const [activePath, setActivePath] = useState(files[0]?.path ?? '');
  const file = files.find((f) => f.path === activePath) ?? files[0];

  return (
    <section className="glass flex min-h-0 flex-col rounded-2xl shadow-panel" aria-label="Code diff">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hull-400/35 px-4 py-3">
        <h2 className="text-sm font-semibold tracking-tight text-slate-100">Applied diff</h2>
        <span
          className={`rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] ${
          applied ? 'border-alert/40 bg-alert/10 text-alert' : 'border-amber/40 bg-amber/10 text-amber'}`
          }>
          
          {applied ? 'written to disk' : 'dry run · not written'}
        </span>
      </div>

      <div
        role="tablist"
        aria-label="Changed files"
        className="thin-scroll flex gap-1 overflow-x-auto border-b border-hull-400/35 px-3 py-2">
        
        {files.map((f) => {
          const active = f.path === file.path;
          const Icon = f.language === 'markdown' ? FileTextIcon : FileCode2Icon;
          return (
            <button
              key={f.path}
              role="tab"
              aria-selected={active}
              onClick={() => setActivePath(f.path)}
              className={`relative flex shrink-0 items-center gap-2 rounded-md px-3 py-2 font-mono text-[11px] transition-colors duration-200 ease-command ${
              active ?
              'bg-electric/10 text-slate-100' :
              'text-mist/70 hover:bg-hull-600/50 hover:text-slate-200'}`
              }>
              
              <Icon className={`h-3.5 w-3.5 ${active ? 'text-electric' : 'text-mist/50'}`} />
              {f.path}
              <span className="text-neon/90">+{f.additions}</span>
              <span className="text-alert/90">-{f.deletions}</span>
              {active &&
              <motion.span
                layoutId="diff-tab"
                className="absolute inset-x-2 -bottom-[9px] h-[2px] rounded-full bg-electric"
                transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }} />

              }
            </button>);

        })}
      </div>

      <div className="thin-scroll min-h-0 flex-1 overflow-auto py-2">
        <table className="w-full border-collapse font-mono text-[11.5px] leading-[1.65]">
          <tbody>
            {file.lines.map((line, i) =>
            <tr key={i} className={LINE_STYLE[line.type]}>
                <td className="w-10 select-none pl-3 pr-1 text-right align-top text-mist/35 tabular-nums">
                  {line.oldNo ?? ''}
                </td>
                <td className="w-10 select-none pr-2 text-right align-top text-mist/35 tabular-nums">
                  {line.newNo ?? ''}
                </td>
                <td
                className={`w-4 select-none pr-1 align-top ${
                line.type === 'add' ?
                'text-neon' :
                line.type === 'del' ?
                'text-alert' :
                'text-mist/40'}`
                }>
                
                  {SIGN[line.type]}
                </td>
                <td
                className={`whitespace-pre-wrap break-words pr-4 align-top ${
                line.type === 'meta' ? 'text-plasma' : 'text-slate-300'}`
                }>
                
                  {line.type === 'meta' ? line.text : highlight(line.text, file.language)}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>);

}