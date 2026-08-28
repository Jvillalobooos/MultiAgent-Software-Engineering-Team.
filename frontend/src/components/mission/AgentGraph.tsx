import { AnimatePresence, motion } from 'framer-motion';
import {
  ClipboardListIcon,
  Code2Icon,
  DraftingCompassIcon,
  FlaskConicalIcon,
  GavelIcon,
  ShieldIcon,
  UserCheckIcon,
  CloudIcon,
  CpuIcon,
  type LucideIcon } from
'lucide-react';
import { AgentId, EdgeKind, Provider } from '../../types/mission';
import { AGENTS, EDGES, EDGE_MAP, NODE_H, NODE_W, VIEW_H, VIEW_W } from '../../data/agents';
import { EDGE_COLOR } from '../../utils/format';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';

export interface ActiveEdge {
  key: number;
  from: AgentId;
  to: AgentId;
  kind: EdgeKind;
  duration: number;
}

interface AgentGraphProps {
  activeAgent: AgentId | null;
  visitedAgents?: AgentId[];
  caption: string;
  providers: Record<AgentId, Provider | null>;
  fallbacks: Record<string, string>;
  activeEdge: ActiveEdge | null;
  visitedEdges: string[];
  dimmed: boolean;
}

const ICONS: Record<AgentId, LucideIcon> = {
  product: ClipboardListIcon,
  architecture: DraftingCompassIcon,
  developer: Code2Icon,
  security: ShieldIcon,
  testing: FlaskConicalIcon,
  reviewer: GavelIcon,
  human_review: UserCheckIcon
};

const ease = [0.23, 1, 0.32, 1] as const;
const PARTICLE_STAGGER = [0, 0.34, 0.67] as const;
const pct = (value: number, total: number) => `${value / total * 100}%`;

function ProviderBadge({
  provider,
  fallback,
  operator
}: {provider: Provider | null;fallback?: string;operator?: boolean;}) {
  if (!provider) {
    return (
      <span className="rounded border border-hull-400/60 px-1.5 py-[2px] font-mono text-[10px] uppercase tracking-[0.12em] text-mist/80">
        {operator ? 'operator' : 'pending'}
      </span>);

  }
  const isCloud = provider === 'cloud';
  const Icon = isCloud ? CloudIcon : CpuIcon;
  return (
    <motion.span
      layout
      title={fallback ? `Fallback: ${fallback}` : undefined}
      transition={{ duration: 0.25, ease }}
      className={`flex items-center gap-1 rounded border px-1.5 py-[2px] font-mono text-[10px] uppercase tracking-[0.12em] transition-colors duration-300 ease-command ${
      isCloud ?
      fallback ?
      'border-amber/55 bg-amber/12 text-amber' :
      'border-plasma/50 bg-plasma/12 text-plasma' :
      'border-neon/45 bg-neon/10 text-neon'}`
      }>
      
      <Icon className="h-2.5 w-2.5" />
      {isCloud ? fallback ? 'cloud ⚡fallback' : 'cloud' : 'ollama · local'}
    </motion.span>);

}

export function AgentGraph({
  activeAgent,
  visitedAgents = [],
  caption,
  providers,
  fallbacks,
  activeEdge,
  visitedEdges,
  dimmed
}: AgentGraphProps) {
  const activeEdgeId = activeEdge ? `${activeEdge.from}-${activeEdge.to}` : null;
  // SMIL ignores the global reduced-motion CSS rule, so the particles have to be
  // withheld here rather than merely slowed down.
  const reducedMotion = usePrefersReducedMotion();

  return (
    <motion.section
      animate={{ opacity: dimmed ? 0.25 : 1, filter: dimmed ? 'blur(3px)' : 'blur(0px)' }}
      transition={{ duration: 0.35, ease }}
      aria-label="Live agent graph"
      className="thin-scroll relative w-full overflow-x-auto">

      <div className="relative mx-auto flex min-w-[1120px] justify-center">
        <div className="relative w-full" style={{ aspectRatio: `${VIEW_W} / ${VIEW_H}` }}>
          <svg
            viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
            className="absolute inset-0 h-full w-full"
            aria-hidden="true">
            
            <defs>
              <filter id="edge-glow" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {EDGES.map((edge) => {
              const isActive = activeEdgeId === edge.id;
              const visited = visitedEdges.includes(edge.id);
              const color = EDGE_COLOR[edge.kind];
              return (
                <g key={edge.id}>
                  <path
                    d={edge.d}
                    fill="none"
                    stroke={color}
                    strokeWidth={isActive ? 2 : 1.2}
                    strokeOpacity={isActive ? 0.95 : visited ? 0.38 : 0.16}
                    strokeDasharray={edge.dashed ? '7 7' : undefined}
                    strokeLinecap="round"
                    filter={isActive ? 'url(#edge-glow)' : undefined}
                    style={{ transition: 'stroke-opacity 300ms cubic-bezier(0.23,1,0.32,1)' }} />
                  
                </g>);

            })}

            {activeEdge && activeEdgeId && EDGE_MAP[activeEdgeId] && !reducedMotion &&
            <g key={`${activeEdge.key}-${activeEdgeId}`}>
                {PARTICLE_STAGGER.map((offset, i) =>
              <circle
                key={i}
                r={i === 0 ? 4.2 : 2.6}
                fill={EDGE_COLOR[activeEdge.kind]}
                opacity={i === 0 ? 0.95 : 0.55}
                filter="url(#edge-glow)">

                    <animateMotion
                  dur={`${activeEdge.duration}ms`}
                  begin={`${Math.round(offset * activeEdge.duration)}ms`}
                  repeatCount="indefinite"
                  calcMode="linear"
                  keyPoints={activeEdge.kind === 'reject' ? '1;0' : '0;1'}
                  keyTimes="0;1"
                  path={EDGE_MAP[activeEdgeId].d} />

                  </circle>
              )}
              </g>
            }
          </svg>

          {AGENTS.map((node) => {
            const Icon = ICONS[node.id];
            const isActive = activeAgent === node.id;
            // Three states, not two: an agent that has already run is finished work,
            // not the same as one the run never reached.
            const isDone = !isActive && visitedAgents.includes(node.id);
            return (
              <div
                key={node.id}
                className="absolute"
                style={{
                  left: pct(node.x - NODE_W / 2, VIEW_W),
                  top: pct(node.y - NODE_H / 2, VIEW_H),
                  width: pct(NODE_W, VIEW_W),
                  height: pct(NODE_H, VIEW_H)
                }}>
                
                <div
                  className={`relative flex h-full w-full flex-col justify-between rounded-xl border px-3 py-2.5 transition-all duration-300 ease-command ${
                  isActive ?
                  'border-electric/70 bg-electric/[0.09] shadow-glow-electric' :
                  isDone ?
                  'border-neon/30 bg-hull-800/70' :
                  'border-hull-400/45 bg-hull-800/40 opacity-60'}`
                  }>
                  
                  {isActive && !reducedMotion &&
                  <>
                      <motion.span
                      aria-hidden
                      className="pointer-events-none absolute -inset-1 rounded-xl border border-electric/25"
                      animate={{ opacity: [0.55, 0.1, 0.55], scale: [1, 1.03, 1] }}
                      transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }} />
                    
                      <span className="pointer-events-none absolute -right-2 -top-2 h-6 w-6">
                        <span className="block h-full w-full animate-spin rounded-full border border-transparent border-t-electric border-r-electric/50 [animation-duration:1.1s]" />
                      </span>
                    </>
                  }
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Icon
                        className={`h-4 w-4 transition-colors duration-300 ease-command ${
                        isActive ? 'text-electric' : isDone ? 'text-neon/75' : 'text-mist/80'}`
                        }
                        strokeWidth={2} />
                      
                      <div className="leading-tight">
                        <div
                          className={`text-[12px] font-semibold tracking-tight transition-colors duration-300 ease-command ${
                          isActive ? 'text-slate-50' : isDone ? 'text-slate-200' : 'text-slate-300/70'}`
                          }>
                          
                          {node.label}
                        </div>
                        <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-mist/80">
                          {node.role}
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <ProviderBadge
                      provider={providers[node.id]}
                      fallback={fallbacks[node.id]}
                      operator={node.id === 'human_review'} />
                    {isActive ?
                    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-electric/80">
                        active
                      </span> :
                    isDone ?
                    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-neon/70">
                        done
                      </span> :
                    null
                    }
                  </div>
                </div>

                <AnimatePresence>
                  {isActive && caption &&
                  <motion.p
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.24, ease }}
                    className={`absolute left-1/2 w-[230px] -translate-x-1/2 rounded-md border border-electric/25 bg-hull-900/85 px-2.5 py-1.5 text-center font-mono text-[10px] leading-snug text-electric/90 backdrop-blur ${
                    node.id === 'human_review' ?
                    'bottom-[calc(100%+10px)]' :
                    'top-[calc(100%+10px)]'}`
                    }>
                    
                      {caption}
                    </motion.p>
                  }
                </AnimatePresence>
              </div>);

          })}

          <div className="pointer-events-none absolute bottom-1 left-2 flex flex-wrap items-center gap-4 font-mono text-[10px] uppercase tracking-[0.14em] text-mist/80">
            <span className="flex items-center gap-1.5">
              <span className="h-[2px] w-5 rounded-full bg-electric" /> forward
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-[2px] w-5 rounded-full" style={{ background: EDGE_COLOR.reject }} />{' '}
              rejection loop
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-[2px] w-5 rounded-full bg-amber" /> human branch
            </span>
          </div>
        </div>
      </div>
    </motion.section>);

}
