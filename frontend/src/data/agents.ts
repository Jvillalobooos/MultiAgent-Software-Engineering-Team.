import { AgentId, AgentNode, GraphEdge, Provider } from '../types/mission';

export const VIEW_W = 1400;
export const VIEW_H = 520;
export const NODE_W = 176;
export const NODE_H = 94;

export const AGENTS: AgentNode[] = [
{ id: 'product', label: 'Product', role: 'spec intake', x: 112, y: 200 },
{ id: 'architecture', label: 'Architecture', role: 'module plan', x: 332, y: 200 },
{ id: 'developer', label: 'Developer', role: 'code synthesis', x: 552, y: 200 },
{ id: 'security', label: 'Security', role: 'policy scan', x: 772, y: 200 },
{ id: 'testing', label: 'Testing', role: 'suite exec', x: 992, y: 200 },
{ id: 'reviewer', label: 'Reviewer', role: 'scoring gate', x: 1212, y: 200 },
{ id: 'human_review', label: 'Human Review', role: 'operator gate', x: 886, y: 412 }];


export const AGENT_MAP: Record<AgentId, AgentNode> = AGENTS.reduce(
  (acc, node) => ({ ...acc, [node.id]: node }),
  {} as Record<AgentId, AgentNode>
);

const straight = (from: AgentId, to: AgentId): string => {
  const a = AGENT_MAP[from];
  const b = AGENT_MAP[to];
  return `M ${a.x + NODE_W / 2 + 6},${a.y} L ${b.x - NODE_W / 2 - 6},${b.y}`;
};

export const EDGES: GraphEdge[] = [
{ id: 'product-architecture', from: 'product', to: 'architecture', kind: 'forward', d: straight('product', 'architecture') },
{ id: 'architecture-developer', from: 'architecture', to: 'developer', kind: 'forward', d: straight('architecture', 'developer') },
{ id: 'developer-security', from: 'developer', to: 'security', kind: 'forward', d: straight('developer', 'security') },
{ id: 'security-testing', from: 'security', to: 'testing', kind: 'forward', d: straight('security', 'testing') },
{ id: 'testing-reviewer', from: 'testing', to: 'reviewer', kind: 'forward', d: straight('testing', 'reviewer') },
{
  id: 'security-human_review',
  from: 'security',
  to: 'human_review',
  kind: 'branch',
  d: 'M 772,252 C 772,340 736,412 794,412'
},
{
  id: 'human_review-testing',
  from: 'human_review',
  to: 'testing',
  kind: 'branch',
  dashed: true,
  d: 'M 978,412 C 1052,412 1010,300 992,252'
},
{
  id: 'reviewer-developer',
  from: 'reviewer',
  to: 'developer',
  kind: 'reject',
  d: 'M 1212,150 C 1166,86 706,74 552,150'
},
{
  id: 'reviewer-architecture',
  from: 'reviewer',
  to: 'architecture',
  kind: 'reject',
  d: 'M 1212,150 C 1140,4 470,-8 332,150'
},
// Routes the real workflow actually takes, recovered from recorded run events:
// after a remediation loop the Developer re-enters Testing directly (Security is
// not re-run), and both Reviewer and Developer can escalate to the operator gate.
{
  id: 'developer-testing',
  from: 'developer',
  to: 'testing',
  kind: 'forward',
  d: 'M 552,248 C 680,322 864,322 992,248'
},
{
  id: 'reviewer-human_review',
  from: 'reviewer',
  to: 'human_review',
  kind: 'branch',
  d: 'M 1212,248 C 1212,364 1092,412 980,412'
},
{
  id: 'developer-human_review',
  from: 'developer',
  to: 'human_review',
  kind: 'branch',
  dashed: true,
  d: 'M 552,248 C 556,394 664,456 796,438'
}];


export const EDGE_MAP: Record<string, GraphEdge> = EDGES.reduce(
  (acc, edge) => ({ ...acc, [edge.id]: edge }),
  {} as Record<string, GraphEdge>
);

export const INITIAL_PROVIDERS: Record<AgentId, Provider | null> = {
  product: 'local',
  architecture: 'local',
  developer: 'local',
  security: 'local',
  testing: 'local',
  reviewer: 'cloud',
  human_review: null
};

export const MODEL_BY_PROVIDER: Record<Provider, string> = {
  local: 'ollama/qwen2.5-coder:14b',
  cloud: 'anthropic/claude-sonnet-4'
};