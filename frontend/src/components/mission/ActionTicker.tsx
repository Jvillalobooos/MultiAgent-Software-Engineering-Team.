import React from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertOctagonIcon,
  BrainCircuitIcon,
  DatabaseIcon,
  RadioTowerIcon,
  WrenchIcon } from
'lucide-react';
import { EventType, RunEvent, ToolStatus } from '../../types/mission';
import { AGENT_LABELS, TOOL_STATUS_CLASS, clampText, formatClock } from '../../utils/format';

interface ActionTickerProps {
  events: RunEvent[];
}

const ease = [0.23, 1, 0.32, 1] as const;

const TYPE_META: Record<
  EventType,
  {label: string;accent: string;text: string;icon: React.ComponentType<{className?: string;}>;}> =
{
  rag: { label: 'RAG retrieval', accent: 'bg-plasma', text: 'text-plasma', icon: DatabaseIcon },
  tool: { label: 'MCP tool call', accent: 'bg-electric', text: 'text-electric', icon: WrenchIcon },
  model: { label: 'Model call', accent: 'bg-neon', text: 'text-neon', icon: BrainCircuitIcon },
  error: { label: 'Error', accent: 'bg-alert', text: 'text-alert', icon: AlertOctagonIcon }
};

function EventCard({ event }: {event: RunEvent;}) {
  const meta = TYPE_META[event.type];
  const Icon = meta.icon;
  const toolStatus = event.metadata.status as ToolStatus | undefined;

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: -18, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.28, ease }}
      className="glass-soft relative overflow-hidden rounded-lg py-2.5 pl-3.5 pr-3">
      
      <span className={`absolute left-0 top-0 h-full w-[2px] ${meta.accent}`} />
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className={`h-3.5 w-3.5 shrink-0 ${meta.text}`} />
          <span className={`truncate font-mono text-[11px] font-medium ${meta.text}`}>
            {event.name}
          </span>
        </div>
        <span className="shrink-0 font-mono text-[10px] tabular-nums text-mist/80">
          {formatClock(event.at)}
        </span>
      </div>

      <p className="mt-1.5 font-mono text-[11px] leading-snug text-slate-300" title={event.status_message}>
        {clampText(event.status_message, 160)}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded border border-hull-400/55 px-1.5 py-[1px] font-mono text-[10px] uppercase tracking-[0.1em] text-mist/80">
          {AGENT_LABELS[event.agent]} · it {event.iteration}
        </span>
        {event.type === 'rag' &&
        <span className="rounded border border-plasma/40 bg-plasma/10 px-1.5 py-[1px] font-mono text-[10px] text-plasma">
            score {Number(event.metadata.relevance).toFixed(2)}
          </span>
        }
        {toolStatus &&
        <span
          className={`rounded border px-1.5 py-[1px] font-mono text-[10px] uppercase tracking-[0.1em] ${TOOL_STATUS_CLASS[toolStatus]}`}>
          
            {toolStatus}
          </span>
        }
        {event.usage_details &&
        <span className="rounded border border-neon/35 bg-neon/[0.07] px-1.5 py-[1px] font-mono text-[10px] text-neon/90">
            {event.usage_details.latency_ms}ms ·{' '}
            {event.usage_details.input_tokens + event.usage_details.output_tokens} tok
          </span>
        }
        {event.type === 'error' &&
        <span className="rounded border border-alert/40 bg-alert/10 px-1.5 py-[1px] font-mono text-[10px] text-alert">
            {String(event.metadata.code)}
          </span>
        }
        {event.model &&
        <span className="rounded border border-plasma/35 bg-plasma/[0.07] px-1.5 py-[1px] font-mono text-[10px] text-plasma/90">
            {event.model}
          </span>
        }
        {event.usage_details &&
        <span className="rounded border border-hull-400/55 px-1.5 py-[1px] font-mono text-[10px] text-mist/80">
            {event.usage_details.input_tokens} in / {event.usage_details.output_tokens} out
          </span>
        }
      </div>

      {(event.input || event.output) &&
      <details className="mt-2">
          <summary className="cursor-pointer rounded font-mono text-[10px] uppercase tracking-[0.12em] text-mist/80 transition-colors hover:text-electric focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-electric">
            payload
          </summary>
          {event.input &&
        <pre className="thin-scroll mt-1.5 max-h-28 overflow-auto whitespace-pre-wrap break-words rounded border border-hull-400/30 bg-hull-900/60 p-2 font-mono text-[10px] leading-snug text-mist">
              {clampText(event.input, 1200)}
            </pre>
        }
          {event.output &&
        <pre className="thin-scroll mt-1.5 max-h-28 overflow-auto whitespace-pre-wrap break-words rounded border border-hull-400/30 bg-hull-900/60 p-2 font-mono text-[10px] leading-snug text-slate-300/80">
              {clampText(event.output, 1200)}
            </pre>
        }
        </details>
      }
    </motion.li>);

}

export function ActionTicker({ events }: ActionTickerProps) {
  return (
    <aside
      aria-label="Live action ticker"
      className="glass flex max-h-[420px] min-h-[240px] flex-col rounded-2xl border-y-0 border-r-0">
      
      <div className="flex items-center justify-between border-b border-hull-400/35 px-4 py-3">
        <h3 className="flex items-center gap-2 text-[12px] font-semibold tracking-tight text-slate-100">
          <RadioTowerIcon className="h-3.5 w-3.5 text-electric" />
          Action ticker
        </h3>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-mist/80">
          {events.length} events
        </span>
      </div>

      <div
        tabIndex={0}
        role="log"
        aria-label="Run events, newest first"
        className="thin-scroll min-h-0 flex-1 overflow-y-auto px-3 py-3 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-electric">
        {events.length === 0 ?
        <p className="mt-6 text-center font-mono text-[11px] text-mist/80">awaiting telemetry…</p> :

        <ul className="flex flex-col gap-2">
            <AnimatePresence initial={false}>
              {[...events].reverse().map((event) =>
            <EventCard key={event.id} event={event} />
            )}
            </AnimatePresence>
          </ul>
        }
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-hull-400/35 px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.12em] text-mist/80">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-plasma" /> rag
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-electric" /> mcp
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-neon" /> model
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-alert" /> error
        </span>
      </div>
    </aside>);

}
