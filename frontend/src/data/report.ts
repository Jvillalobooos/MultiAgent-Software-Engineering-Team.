import { ChangedFile, FinalReport } from '../types/mission';

const calculatorDiff: ChangedFile = {
  path: 'src/calculator.py',
  language: 'python',
  additions: 38,
  deletions: 9,
  lines: [
  { type: 'meta', text: '@@ -1,14 +1,26 @@ core evaluation' },
  { type: 'ctx', text: '"""Calculator core for calculadora-qa-demo."""', oldNo: 1, newNo: 1 },
  { type: 'ctx', text: 'from __future__ import annotations', oldNo: 2, newNo: 2 },
  { type: 'del', text: 'import re', oldNo: 3 },
  { type: 'add', text: 'from dataclasses import dataclass', newNo: 3 },
  { type: 'add', text: 'from .parser import ExpressionParser, Token', newNo: 4 },
  { type: 'ctx', text: '', oldNo: 4, newNo: 5 },
  { type: 'add', text: '@dataclass(frozen=True)', newNo: 6 },
  { type: 'add', text: 'class SafeEvaluator:', newNo: 7 },
  { type: 'add', text: '    """Evaluates a parsed token stream without eval()."""', newNo: 8 },
  { type: 'add', text: '    max_depth: int = 32', newNo: 9 },
  { type: 'add', text: '', newNo: 10 },
  { type: 'ctx', text: 'class Calculator:', oldNo: 5, newNo: 11 },
  { type: 'del', text: '    def parse_expression(self, raw: str):', oldNo: 6 },
  { type: 'del', text: '        # NOTE: fast path, trusted input only', oldNo: 7 },
  { type: 'del', text: '        return eval(re.sub(r"[^0-9+\\-*/(). ]", "", raw))', oldNo: 8 },
  { type: 'add', text: '    def __init__(self, parser: ExpressionParser | None = None) -> None:', newNo: 12 },
  { type: 'add', text: '        self._parser = parser or ExpressionParser()', newNo: 13 },
  { type: 'add', text: '        self._evaluator = SafeEvaluator()', newNo: 14 },
  { type: 'add', text: '', newNo: 15 },
  { type: 'add', text: '    def parse_expression(self, raw: str) -> list[Token]:', newNo: 16 },
  { type: 'add', text: '        if not raw or not raw.strip():', newNo: 17 },
  { type: 'add', text: '            raise ValueError("expression must not be empty")', newNo: 18 },
  { type: 'add', text: '        return self._parser.tokenize(raw)', newNo: 19 },
  { type: 'ctx', text: '', oldNo: 9, newNo: 20 },
  { type: 'ctx', text: '    def divide(self, a: float, b: float) -> float:', oldNo: 10, newNo: 21 },
  { type: 'del', text: '        return a / b', oldNo: 11 },
  { type: 'add', text: '        if b == 0:', newNo: 22 },
  { type: 'add', text: '            raise ValueError("division by zero is not defined")', newNo: 23 },
  { type: 'add', text: '        return a / b', newNo: 24 },
  { type: 'ctx', text: '', oldNo: 12, newNo: 25 },
  { type: 'ctx', text: '    def evaluate(self, raw: str) -> float:', oldNo: 13, newNo: 26 },
  { type: 'del', text: '        return float(self.parse_expression(raw))', oldNo: 14 },
  { type: 'add', text: '        return self._evaluator.reduce(self.parse_expression(raw))', newNo: 27 }]

};

const parserDiff: ChangedFile = {
  path: 'src/parser.py',
  language: 'python',
  additions: 24,
  deletions: 0,
  lines: [
  { type: 'meta', text: '@@ -0,0 +1,24 @@ new module' },
  { type: 'add', text: '"""Tokenizer extracted from the evaluation core (iteration 2)."""', newNo: 1 },
  { type: 'add', text: 'from dataclasses import dataclass', newNo: 2 },
  { type: 'add', text: '', newNo: 3 },
  { type: 'add', text: 'ALLOWED = set("0123456789+-*/(). ")', newNo: 4 },
  { type: 'add', text: '', newNo: 5 },
  { type: 'add', text: '@dataclass(frozen=True)', newNo: 6 },
  { type: 'add', text: 'class Token:', newNo: 7 },
  { type: 'add', text: '    kind: str', newNo: 8 },
  { type: 'add', text: '    value: str', newNo: 9 },
  { type: 'add', text: '', newNo: 10 },
  { type: 'add', text: 'class ExpressionParser:', newNo: 11 },
  { type: 'add', text: '    def tokenize(self, raw: str) -> list[Token]:', newNo: 12 },
  { type: 'add', text: '        invalid = set(raw) - ALLOWED', newNo: 13 },
  { type: 'add', text: '        if invalid:', newNo: 14 },
  { type: 'add', text: '            raise ValueError(f"illegal characters: {sorted(invalid)}")', newNo: 15 },
  { type: 'add', text: '        return [Token("char", c) for c in raw if c != " "]', newNo: 16 }]

};

const testDiff: ChangedFile = {
  path: 'tests/test_calculator.py',
  language: 'python',
  additions: 27,
  deletions: 2,
  lines: [
  { type: 'meta', text: '@@ -1,10 +1,35 @@ boundary coverage' },
  { type: 'ctx', text: 'import pytest', oldNo: 1, newNo: 1 },
  { type: 'ctx', text: 'from src.calculator import Calculator', oldNo: 2, newNo: 2 },
  { type: 'ctx', text: '', oldNo: 3, newNo: 3 },
  { type: 'del', text: 'def test_divide_by_zero():', oldNo: 4 },
  { type: 'del', text: '    with pytest.raises(ZeroDivisionError):', oldNo: 5 },
  { type: 'add', text: '@pytest.fixture', newNo: 4 },
  { type: 'add', text: 'def calc() -> Calculator:', newNo: 5 },
  { type: 'add', text: '    return Calculator()', newNo: 6 },
  { type: 'add', text: '', newNo: 7 },
  { type: 'add', text: 'def test_divide_by_zero(calc):', newNo: 8 },
  { type: 'add', text: '    with pytest.raises(ValueError, match="division by zero"):', newNo: 9 },
  { type: 'ctx', text: '        Calculator().divide(1, 0)', oldNo: 6, newNo: 10 },
  { type: 'ctx', text: '', oldNo: 7, newNo: 11 },
  { type: 'add', text: '@pytest.mark.parametrize("raw", ["", "   ", None])', newNo: 12 },
  { type: 'add', text: 'def test_empty_expression_rejected(calc, raw):', newNo: 13 },
  { type: 'add', text: '    with pytest.raises(ValueError):', newNo: 14 },
  { type: 'add', text: '        calc.parse_expression(raw)', newNo: 15 },
  { type: 'add', text: '', newNo: 16 },
  { type: 'add', text: 'def test_illegal_characters_rejected(calc):', newNo: 17 },
  { type: 'add', text: '    with pytest.raises(ValueError, match="illegal characters"):', newNo: 18 },
  { type: 'add', text: '        calc.parse_expression("2 + $x")', newNo: 19 }]

};

const readmeDiff: ChangedFile = {
  path: 'README.md',
  language: 'markdown',
  additions: 6,
  deletions: 1,
  lines: [
  { type: 'meta', text: '@@ -12,7 +12,12 @@ Usage' },
  { type: 'ctx', text: '## Usage', oldNo: 12, newNo: 12 },
  { type: 'ctx', text: '', oldNo: 13, newNo: 13 },
  { type: 'del', text: 'Expressions are evaluated directly via `eval`.', oldNo: 14 },
  { type: 'add', text: 'Expressions are tokenized by `ExpressionParser`, then reduced by', newNo: 14 },
  { type: 'add', text: '`SafeEvaluator`. `eval` is never used.', newNo: 15 },
  { type: 'add', text: '', newNo: 16 },
  { type: 'add', text: '### Errors', newNo: 17 },
  { type: 'add', text: '- `ValueError` — empty input, illegal characters, division by zero.', newNo: 18 },
  { type: 'add', text: '- Coverage gate: 85% minimum on `src/`.', newNo: 19 }]

};

export const FINAL_REPORT: FinalReport = {
  applied_diff: false,
  workspace_changed: false,
  source_applied: false,
  changed_files: [calculatorDiff, parserDiff, testDiff, readmeDiff],
  review: {
    status: 'APPROVED',
    score: 92,
    subscores: {
      requirements: 95,
      architecture: 91,
      security: 96,
      testing: 88,
      implementation: 90,
      rag_grounding: 93
    },
    problems: [
    'Coverage on src/parser.py sits at 87% — just above the gate.',
    'Security exception for iteration 1 is recorded but scoped to this run only.'],

    reason:
    'Parser/evaluator split resolves the layering violation, eval() is fully removed, and the 22-case suite passes with 93% coverage. Approved for authorized write.'
  },
  route_history: [
  {
    iteration: 1,
    from: 'reviewer',
    to: 'architecture',
    decision: 'REJECTED',
    score: 54,
    reason:
    'Layering violation: parse_expression() reaches eval() inside the evaluation core, and divide() has no zero guard.',
    at: '00:16.4'
  },
  {
    iteration: 2,
    from: 'reviewer',
    to: 'developer',
    decision: 'REJECTED',
    score: 71,
    reason:
    'Architecture accepted, but coverage on src/calculator.py is 78% against an 85% gate — boundary cases missing.',
    at: '00:27.9'
  },
  {
    iteration: 3,
    from: 'reviewer',
    to: 'reviewer',
    decision: 'APPROVED',
    score: 92,
    reason: 'All gates satisfied. 22 tests pass, coverage 93%, security scan clean.',
    at: '00:36.2'
  }],

  model_usage: [
  { agent: 'product', model: 'ollama/qwen2.5-coder:14b', provider: 'local', calls: 1, input_tokens: 986, output_tokens: 412, avg_latency_ms: 1420 },
  { agent: 'architecture', model: 'ollama/qwen2.5-coder:14b', provider: 'local', calls: 2, input_tokens: 3392, output_tokens: 1635, avg_latency_ms: 2095 },
  { agent: 'developer', model: 'anthropic/claude-sonnet-4', provider: 'cloud', calls: 3, input_tokens: 12310, output_tokens: 6354, avg_latency_ms: 2843 },
  { agent: 'reviewer', model: 'anthropic/claude-sonnet-4', provider: 'cloud', calls: 3, input_tokens: 16590, output_tokens: 3890, avg_latency_ms: 2443 }],

  errors: [
  { code: 'E_LOCAL_CTX_OVERFLOW', message: 'Local model context exceeded — fell back to cloud provider', agent: 'developer', iteration: 1 },
  { code: 'E_SEC_POLICY', message: 'eval() reachable from parse_expression() — operator gate required', agent: 'security', iteration: 1 },
  { code: 'E_TEST_ASSERT', message: 'test_divide_by_zero: expected ValueError, got ZeroDivisionError', agent: 'testing', iteration: 1 },
  { code: 'E_TEST_COVERAGE', message: 'coverage 78% below 85% gate for src/calculator.py', agent: 'testing', iteration: 2 }],

  rag_evidence: [
  { source: 'SPEC-STANDARDS.md', section: 'Acceptance criteria', score: 0.91, agent: 'product', snippet: 'Every public method must define its failure mode as a typed exception.' },
  { source: 'ARCHITECTURE-GUIDE.md', section: 'Parser/evaluator split', score: 0.93, agent: 'architecture', snippet: 'Parsing and evaluation must not share a module; tokenizers stay side-effect free.' },
  { source: 'SECURITY-POLICY.md', section: 'Escalation matrix §4.2', score: 0.94, agent: 'security', snippet: 'Dynamic execution primitives require a human operator exception, scoped per run.' },
  { source: 'REVIEW-RUBRIC.md', section: 'Approval threshold', score: 0.96, agent: 'reviewer', snippet: 'Approve at ≥85 total with no subscore below 80 and a clean security scan.' },
  { source: 'TEST-PLAYBOOK.md', section: 'Boundary matrix', score: 0.82, agent: 'testing', snippet: 'Parametrize empty, whitespace, and null inputs for every parser entry point.' }],

  tool_results: [
  { name: 'write_file', status: 'SUCCESS', duration_ms: 84, agent: 'developer', detail: 'src/calculator.py staged (dry run)' },
  { name: 'run_security_scan', status: 'SUCCESS', duration_ms: 1640, agent: 'security', detail: '0 critical · 2 medium findings' },
  { name: 'dependency_audit', status: 'DENIED', duration_ms: 12, agent: 'security', detail: 'network egress blocked by policy' },
  { name: 'request_human_approval', status: 'SUCCESS', duration_ms: 2410, agent: 'human_review', detail: 'operator granted scoped exception' },
  { name: 'run_tests', status: 'FAIL', duration_ms: 3180, agent: 'testing', detail: '11 passed · 3 failed' },
  { name: 'run_tests', status: 'SUCCESS', duration_ms: 3040, agent: 'testing', detail: '22 passed · coverage 93%' }]

};

export const SUBSCORE_LABELS: Record<keyof FinalReport['review']['subscores'], string> = {
  requirements: 'Requirements',
  architecture: 'Architecture',
  security: 'Security',
  testing: 'Testing',
  implementation: 'Implementation',
  rag_grounding: 'RAG grounding'
};