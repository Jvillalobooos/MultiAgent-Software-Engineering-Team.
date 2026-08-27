import { Beat } from '../types/mission';

export const MAX_ITERATIONS = 3;
export const RUN_ID = 'run_9f2c-ac71-mc';

const model = (
provider: 'Ollama · Local' | 'Cloud · Anthropic',
name: string,
latency: number,
input: number,
output: number) => (
{
  name: 'model_call',
  type: 'model' as const,
  level: 'info' as const,
  status_message: `${provider} · ${latency}ms · ${input + output} tok`,
  metadata: { provider, latency_ms: latency },
  model: name,
  usage_details: { input_tokens: input, output_tokens: output, latency_ms: latency }
});

const rag = (source: string, section: string, score: number) => ({
  name: 'rag_retrieval',
  type: 'rag' as const,
  level: 'info' as const,
  status_message: `${source} · ${section}`,
  metadata: { source, section, relevance: score }
});

const tool = (
name: string,
status: 'SUCCESS' | 'FAIL' | 'DENIED',
duration: number,
detail: string) => (
{
  name,
  type: 'tool' as const,
  level: status === 'SUCCESS' ? 'info' as const : 'warn' as const,
  status_message: detail,
  metadata: { status, duration_ms: duration, transport: 'mcp/stdio' }
});

const error = (code: string, message: string) => ({
  name: code,
  type: 'error' as const,
  level: 'error' as const,
  status_message: message,
  metadata: { code }
});

export const BEATS: Beat[] = [
{
  agent: 'product',
  caption: 'Product — parsing specification into acceptance criteria...',
  duration: 2200,
  iteration: 1,
  events: [
  rag('SPEC-STANDARDS.md', 'Acceptance criteria', 0.91),
  model('Ollama · Local', 'ollama/qwen2.5-coder:14b', 1420, 986, 412)]

},
{
  agent: 'architecture',
  caption: 'Architecture — drafting module boundaries for calculator core...',
  duration: 2200,
  iteration: 1,
  edge: { from: 'product', to: 'architecture', kind: 'forward' },
  events: [
  rag('ARCHITECTURE-GUIDE.md', 'Layered python services', 0.87),
  model('Ollama · Local', 'ollama/qwen2.5-coder:14b', 1980, 1512, 733)]

},
{
  agent: 'developer',
  caption: 'Developer — synthesizing src/calculator.py...',
  duration: 2400,
  iteration: 1,
  edge: { from: 'architecture', to: 'developer', kind: 'forward' },
  providerFlip: { agent: 'developer', provider: 'cloud', reason: 'local context window exceeded' },
  events: [
  error('E_LOCAL_CTX_OVERFLOW', 'Local model context exceeded — falling back to cloud provider'),
  model('Cloud · Anthropic', 'anthropic/claude-sonnet-4', 3120, 4210, 1864),
  tool('write_file', 'SUCCESS', 84, 'src/calculator.py staged (dry run)')]

},
{
  agent: 'security',
  caption: 'Security — running run_security_scan...',
  duration: 2200,
  iteration: 1,
  events: [
  { ...tool('run_security_scan', 'SUCCESS', 1640, '0 critical · 2 medium findings') },
  tool('dependency_audit', 'DENIED', 12, 'network egress blocked by policy'),
  error('E_SEC_POLICY', 'eval() reachable from parse_expression() — operator gate required')],

  edge: { from: 'developer', to: 'security', kind: 'forward' }
},
{
  agent: 'human_review',
  caption: 'Human Review — awaiting operator sign-off on security exception...',
  duration: 2600,
  iteration: 1,
  status: 'HUMAN_REVIEW_REQUIRED',
  edge: { from: 'security', to: 'human_review', kind: 'branch' },
  events: [
  tool('request_human_approval', 'SUCCESS', 2410, 'operator granted scoped exception'),
  rag('SECURITY-POLICY.md', 'Escalation matrix §4.2', 0.94)]

},
{
  agent: 'testing',
  caption: 'Testing — executing pytest suite (14 cases)...',
  duration: 2400,
  iteration: 1,
  status: 'RUNNING',
  edge: { from: 'human_review', to: 'testing', kind: 'branch' },
  events: [
  tool('run_tests', 'FAIL', 3180, '11 passed · 3 failed'),
  error('E_TEST_ASSERT', 'test_divide_by_zero: expected ValueError, got ZeroDivisionError')]

},
{
  agent: 'reviewer',
  caption: 'Reviewer — scoring iteration 1 against rubric...',
  duration: 2400,
  iteration: 1,
  status: 'REJECTED',
  edge: { from: 'testing', to: 'reviewer', kind: 'forward' },
  events: [
  rag('REVIEW-RUBRIC.md', 'Scoring weights', 0.89),
  model('Cloud · Anthropic', 'anthropic/claude-sonnet-4', 2640, 5120, 1290),
  error('E_REVIEW_REJECT', 'Score 54/100 — layering violation, returning to Architecture')]

},
{
  agent: 'architecture',
  caption: 'Architecture — re-partitioning parser out of the evaluation core...',
  duration: 2400,
  iteration: 2,
  status: 'RUNNING',
  edge: { from: 'reviewer', to: 'architecture', kind: 'reject' },
  events: [
  rag('ARCHITECTURE-GUIDE.md', 'Parser/evaluator split', 0.93),
  model('Ollama · Local', 'ollama/qwen2.5-coder:14b', 2210, 1880, 902)]

},
{
  agent: 'developer',
  caption: 'Developer — implementing SafeEvaluator + guard clauses...',
  duration: 2200,
  iteration: 2,
  edge: { from: 'architecture', to: 'developer', kind: 'forward' },
  events: [
  model('Cloud · Anthropic', 'anthropic/claude-sonnet-4', 2870, 3980, 2110),
  tool('write_file', 'SUCCESS', 71, 'src/calculator.py updated (dry run)')]

},
{
  agent: 'security',
  caption: 'Security — re-running run_security_scan on patched tree...',
  duration: 2000,
  iteration: 2,
  edge: { from: 'developer', to: 'security', kind: 'forward' },
  events: [tool('run_security_scan', 'SUCCESS', 1490, '0 critical · 0 medium findings')]
},
{
  agent: 'testing',
  caption: 'Testing — executing pytest suite (18 cases)...',
  duration: 2200,
  iteration: 2,
  edge: { from: 'security', to: 'testing', kind: 'forward' },
  events: [
  tool('run_tests', 'FAIL', 2960, '17 passed · 1 failed'),
  error('E_TEST_COVERAGE', 'coverage 78% below 85% gate for src/calculator.py')]

},
{
  agent: 'reviewer',
  caption: 'Reviewer — scoring iteration 2 against rubric...',
  duration: 2400,
  iteration: 2,
  status: 'REJECTED',
  edge: { from: 'testing', to: 'reviewer', kind: 'forward' },
  events: [
  model('Cloud · Anthropic', 'anthropic/claude-sonnet-4', 2410, 5460, 1180),
  error('E_REVIEW_REJECT', 'Score 71/100 — coverage gate, returning to Developer')]

},
{
  agent: 'developer',
  caption: 'Developer — adding boundary tests + docstrings...',
  duration: 2200,
  iteration: 3,
  status: 'RUNNING',
  edge: { from: 'reviewer', to: 'developer', kind: 'reject' },
  events: [
  model('Cloud · Anthropic', 'anthropic/claude-sonnet-4', 2540, 4120, 2380),
  tool('write_file', 'SUCCESS', 66, 'tests/test_calculator.py updated (dry run)')]

},
{
  agent: 'security',
  caption: 'Security — verifying no new policy surface...',
  duration: 1800,
  iteration: 3,
  edge: { from: 'developer', to: 'security', kind: 'forward' },
  events: [tool('run_security_scan', 'SUCCESS', 1220, 'clean · policy hash unchanged')]
},
{
  agent: 'testing',
  caption: 'Testing — executing pytest suite (22 cases)...',
  duration: 2000,
  iteration: 3,
  edge: { from: 'security', to: 'testing', kind: 'forward' },
  events: [tool('run_tests', 'SUCCESS', 3040, '22 passed · coverage 93%')]
},
{
  agent: 'reviewer',
  caption: 'Reviewer — final scoring · compiling mission debrief...',
  duration: 2600,
  iteration: 3,
  status: 'APPROVED',
  edge: { from: 'testing', to: 'reviewer', kind: 'forward' },
  events: [
  rag('REVIEW-RUBRIC.md', 'Approval threshold', 0.96),
  model('Cloud · Anthropic', 'anthropic/claude-sonnet-4', 2280, 6010, 1420),
  {
    name: 'review_approved',
    type: 'model',
    level: 'info',
    status_message: 'Score 92/100 — run approved',
    metadata: { score: 92 },
    model: 'anthropic/claude-sonnet-4'
  }]

}];