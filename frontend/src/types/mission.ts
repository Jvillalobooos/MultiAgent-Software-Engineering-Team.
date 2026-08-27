export type AgentId =
'product' |
'architecture' |
'developer' |
'security' |
'testing' |
'reviewer' |
'human_review';

export type RunStatus = 'RUNNING' | 'APPROVED' | 'REJECTED' | 'HUMAN_REVIEW_REQUIRED';

export type Provider = 'local' | 'cloud';

export type EventType = 'rag' | 'tool' | 'model' | 'error';

export type EventLevel = 'info' | 'warn' | 'error';

export type ToolStatus = 'SUCCESS' | 'FAIL' | 'DENIED';

export interface UsageDetails {
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
}

/** Event: {name, type, level, status_message, metadata, model, input, output, usage_details} */
export interface RunEvent {
  id: string;
  name: string;
  type: EventType;
  level: EventLevel;
  status_message: string;
  metadata: Record<string, string | number>;
  model?: string;
  input?: string;
  output?: string;
  usage_details?: UsageDetails;
  agent: AgentId;
  iteration: number;
  at: number;
}

export type RunEventSeed = Omit<RunEvent, 'id' | 'agent' | 'iteration' | 'at'>;

export type EdgeKind = 'forward' | 'reject' | 'branch';

export interface Beat {
  agent: AgentId;
  caption: string;
  duration: number;
  iteration: number;
  status?: RunStatus;
  edge?: {from: AgentId;to: AgentId;kind: EdgeKind;};
  providerFlip?: {agent: AgentId;provider: Provider;reason: string;};
  events: RunEventSeed[];
}

export interface AgentNode {
  id: AgentId;
  label: string;
  role: string;
  x: number;
  y: number;
}

export interface GraphEdge {
  id: string;
  from: AgentId;
  to: AgentId;
  kind: EdgeKind;
  d: string;
  dashed?: boolean;
}

/* ---------- Final report ---------- */

export type DiffLineType = 'add' | 'del' | 'ctx' | 'meta';

export interface DiffLine {
  type: DiffLineType;
  text: string;
  oldNo?: number;
  newNo?: number;
}

export interface ChangedFile {
  path: string;
  language: 'python' | 'markdown';
  additions: number;
  deletions: number;
  lines: DiffLine[];
}

export interface RouteStep {
  iteration: number;
  from: AgentId;
  to: AgentId;
  decision: 'REJECTED' | 'APPROVED' | 'ESCALATED';
  reason: string;
  score: number;
  at: string;
}

export interface ModelUsage {
  agent: AgentId;
  model: string;
  provider: Provider;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  avg_latency_ms: number;
}

export type SubscoreKey =
'requirements' |
'architecture' |
'security' |
'testing' |
'implementation' |
'rag_grounding';

export interface ReviewResult {
  status: RunStatus;
  score: number;
  subscores: Record<SubscoreKey, number>;
  problems: string[];
  reason: string;
}

export interface RagEvidence {
  source: string;
  section: string;
  score: number;
  agent: AgentId;
  snippet: string;
}

export interface ToolResult {
  name: string;
  status: ToolStatus;
  duration_ms: number;
  agent: AgentId;
  detail: string;
}

export interface RunError {
  code: string;
  message: string;
  agent: AgentId;
  iteration: number;
}

export interface FinalReport {
  route_history: RouteStep[];
  model_usage: ModelUsage[];
  changed_files: ChangedFile[];
  applied_diff: boolean;
  review: ReviewResult;
  errors: RunError[];
  rag_evidence: RagEvidence[];
  tool_results: ToolResult[];
}

export interface LaunchConfig {
  projectPath: string;
  specification: string;
  testSpecification: string;
  writeMode: 'dry_run' | 'authorized';
}