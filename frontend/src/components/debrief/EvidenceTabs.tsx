import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { AlertOctagonIcon, DatabaseIcon, WrenchIcon } from 'lucide-react';
import { RagEvidence, RunError, ToolResult } from '../../types/mission';
import { AGENT_LABELS, TOOL_STATUS_CLASS } from '../../utils/format';

interface EvidenceTabsProps {
  rag: RagEvidence[];
  tools: ToolResult[];
  errors: RunError[];
}

type TabKey = 'rag' | 'tools' | 'errors';

const ease = [0.23, 1, 0.32, 1] as const;

export function EvidenceTabs({ rag, tools, errors }: EvidenceTabsProps) {
  const [tab, setTab] = useState<TabKey>('rag');

  const tabs: {key: TabKey;label: string;count: number;icon: React.ComponentType<{className?: string;}>;}[] = [
  { key: 'rag', label: 'RAG documents cited', count: rag.length, icon: DatabaseIcon },
  { key: 'tools', label: 'MCP tools executed', count: tools.length, icon: WrenchIcon },
  { key: 'errors', label: 'Errors', count: errors.length, icon: AlertOctagonIcon }];


  return (
    <section className="glass rounded-2xl shadow-panel" aria-label="Run evidence">
      <div role="tablist" aria-label="Evidence" className="thin-scroll flex gap-1 overflow-x-auto border-b border-hull-400/35 px-3 py-2">
        {tabs.map(({ key, label, count, icon: Icon }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              role="tab"
              aria-selected={active}
              onClick={() => setTab(key)}
              className={`relative flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-[12px] transition-colors duration-200 ease-command ${
              active ? 'bg-electric/10 text-slate-100' : 'text-mist/70 hover:bg-hull-600/50 hover:text-slate-200'}`
              }>
              
              <Icon className={`h-3.5 w-3.5 ${active ? 'text-electric' : 'text-mist/50'}`} />
              {label}
              <span className="font-mono text-[10px] text-mist/55">{count}</span>
              {active &&
              <motion.span
                layoutId="evidence-tab"
                className="absolute inset-x-2 -bottom-[9px] h-[2px] rounded-full bg-electric"
                transition={{ duration: 0.22, ease }} />

              }
            </button>);

        })}
      </div>

      <div className="thin-scroll max-h-[300px] overflow-y-auto p-3">
        {tab === 'rag' &&
        <ul className="flex flex-col gap-2">
            {rag.map((doc) =>
          <li key={`${doc.source}-${doc.section}`} className="glass-soft rounded-lg p-3">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className="font-mono text-[11.5px] text-plasma">{doc.source}</span>
                  <span className="font-mono text-[11px] text-mist/70">{doc.section}</span>
                  <span className="ml-auto rounded border border-plasma/40 bg-plasma/10 px-1.5 py-[1px] font-mono text-[10px] tabular-nums text-plasma">
                    {doc.score.toFixed(2)}
                  </span>
                </div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-slate-300">{doc.snippet}</p>
                <span className="mt-1.5 inline-block font-mono text-[9.5px] uppercase tracking-[0.12em] text-mist/50">
                  cited by {AGENT_LABELS[doc.agent]}
                </span>
              </li>
          )}
          </ul>
        }

        {tab === 'tools' &&
        <table className="w-full border-collapse text-left">
            <thead>
              <tr className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-mist/50">
                <th className="px-3 py-2 font-medium">tool</th>
                <th className="px-3 py-2 font-medium">status</th>
                <th className="px-3 py-2 font-medium">duration</th>
                <th className="px-3 py-2 font-medium">agent</th>
                <th className="px-3 py-2 font-medium">detail</th>
              </tr>
            </thead>
            <tbody>
              {tools.map((t, i) =>
            <tr key={`${t.name}-${i}`} className="border-t border-hull-400/30">
                  <td className="px-3 py-2.5 font-mono text-[11.5px] text-electric">{t.name}</td>
                  <td className="px-3 py-2.5">
                    <span
                  className={`rounded border px-1.5 py-[1px] font-mono text-[9.5px] uppercase tracking-[0.1em] ${TOOL_STATUS_CLASS[t.status]}`}>
                  
                      {t.status}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-[11px] tabular-nums text-slate-300">
                    {t.duration_ms}ms
                  </td>
                  <td className="px-3 py-2.5 text-[12px] text-mist/85">{AGENT_LABELS[t.agent]}</td>
                  <td className="px-3 py-2.5 text-[12px] text-slate-300">{t.detail}</td>
                </tr>
            )}
            </tbody>
          </table>
        }

        {tab === 'errors' &&
        <ul className="flex flex-col gap-2">
            {errors.map((err, i) =>
          <li key={`${err.code}-${i}`} className="glass-soft rounded-lg border-l-2 border-l-alert/60 p-3">
                <div className="flex flex-wrap items-center gap-x-2.5">
                  <span className="font-mono text-[11.5px] text-alert">{err.code}</span>
                  <span className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-mist/55">
                    {AGENT_LABELS[err.agent]} · iteration {err.iteration}
                  </span>
                </div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-slate-300">{err.message}</p>
              </li>
          )}
          </ul>
        }
      </div>
    </section>);

}