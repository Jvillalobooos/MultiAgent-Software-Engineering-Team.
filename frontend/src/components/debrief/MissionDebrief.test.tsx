import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MissionDebrief } from './MissionDebrief';
import { FinalReport } from '../../types/mission';

const baseReport = (): FinalReport => ({
  route_history: [],
  model_usage: [],
  changed_files: [{
    path: 'app.py', language: 'python', additions: 1, deletions: 1,
    lines: [{ type: 'del', text: 'old', oldNo: 1 },
            { type: 'add', text: 'new', newNo: 1 }],
  }],
  applied_diff: false,
  workspace_changed: false,
  source_applied: false,
  review: {
    status: 'APPROVED', score: 100,
    subscores: {
      requirements: 100, architecture: 100, security: 100,
      testing: 100, implementation: 100, rag_grounding: 100,
    },
    problems: [], reason: 'approved',
  },
  errors: [], rag_evidence: [], tool_results: [],
});

describe('MissionDebrief', () => {
  it('renders a provider warning for a model-usage entry with error_category/http_status', () => {
    const report: FinalReport = {
      ...baseReport(),
      model_usage: [{
        agent: 'product', model: 'gemini-3.7-flash', provider: 'cloud', calls: 1,
        input_tokens: 10, output_tokens: 20, avg_latency_ms: 80,
        http_status: 503, error_category: 'provider_unavailable', retryable: true,
      }],
    };

    render(<MissionDebrief report={report} runId="run-1" projectPath="C:\\projects\\demo" />);

    expect(screen.getByRole('alert')).toHaveTextContent(/provider_unavailable/i);
    expect(screen.getByRole('alert')).toHaveTextContent(/HTTP 503/);
    expect(screen.getByRole('alert')).toHaveTextContent(/retryable/i);
  });

  it('shows a recovered indicator when a fallback later succeeded', () => {
    const report: FinalReport = {
      ...baseReport(),
      model_usage: [{
        agent: 'product', model: 'qwen3.5:4b', provider: 'local', calls: 1,
        input_tokens: 10, output_tokens: 20, avg_latency_ms: 120,
        fallback_succeeded: true,
      }],
    };

    render(<MissionDebrief report={report} runId="run-1" projectPath="C:\\projects\\demo" />);

    expect(screen.getByText(/later fallback attempt.*succeeded/i)).toBeInTheDocument();
  });

  it('renders no provider warning when a model-usage entry has no diagnostics', () => {
    const report: FinalReport = {
      ...baseReport(),
      model_usage: [{
        agent: 'product', model: 'qwen3.5:4b', provider: 'local', calls: 1,
        input_tokens: 10, output_tokens: 20, avg_latency_ms: 120,
      }],
    };

    render(<MissionDebrief report={report} runId="run-1" projectPath="C:\\projects\\demo" />);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders an incomplete backend diff without crashing the workspace', () => {
    const report = baseReport();
    report.changed_files = [{
      path: 'calculadora/operaciones.py', language: 'python', additions: 0, deletions: 0,
    } as unknown as FinalReport['changed_files'][number]];

    render(<MissionDebrief report={report} runId="run-1" projectPath="C:\\projects\\demo" />);

    // The file is named as a target but carries no hunks: a real early-exit outcome,
    // reported as such rather than as a rendering failure.
    expect(screen.getByText(/no changes were recorded for/i)).toBeInTheDocument();
    expect(screen.getByText('calculadora/operaciones.py', { selector: 'span' })).toBeInTheDocument();
  });
});
