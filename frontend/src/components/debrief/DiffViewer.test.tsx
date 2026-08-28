import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DiffViewer } from './DiffViewer';
import { ApplyResult } from '../../types/mission';

describe('DiffViewer write provenance', () => {
  it('does not call workspace writes an update of the selected project', () => {
    render(<DiffViewer files={[]} workspaceChanged sourceApplied={false} />);
    expect(screen.getByRole('region', { name: 'Code diff' })).toHaveTextContent('Workspace only · project unchanged');
    expect(screen.queryByText('Applied to project')).not.toBeInTheDocument();
  });

  it('identifies changes applied to the selected project', () => {
    render(<DiffViewer files={[]} workspaceChanged sourceApplied />);
    expect(screen.getByRole('region', { name: 'Code diff' })).toHaveTextContent('Applied to project');
  });

  it('labels unexecuted changes as proposals, not as an applied diff', () => {
    render(<DiffViewer files={[]} workspaceChanged={false} sourceApplied={false} />);
    expect(screen.getByRole('region', { name: 'Code diff' })).toHaveTextContent('Proposed · no files written');
    expect(screen.getByRole('heading', { name: 'Code changes' })).toBeInTheDocument();
  });

  it.each([
    ['apply_failed', 1, ['app.py'], 'Verification failed · project changes retained'],
    ['apply_failed', null, [], 'Apply failed · check project state'],
    ['restored', null, ['app.py'], 'Restored from backup'],
    ['conflict', null, [], 'Apply/restore conflict · review project state'],
  ] as const)('does not confuse %s with an unchanged project', (status, exitCode, paths, label) => {
    const result: ApplyResult = {
      status, test_exit_code: exitCode, written_paths: [...paths],
      backup_path: 'backup', test_output: '', message: 'Result',
    };
    render(<DiffViewer files={[]} workspaceChanged sourceApplied={false} applyResult={result} />);
    expect(screen.getByRole('region', { name: 'Code diff' })).toHaveTextContent(label);
    expect(screen.queryByText('Workspace only · project unchanged')).not.toBeInTheDocument();
  });

  it('shows application in progress without claiming the project is unchanged', () => {
    render(<DiffViewer files={[]} workspaceChanged sourceApplied={false} phase="applying" />);
    expect(screen.getByRole('region', { name: 'Code diff' })).toHaveTextContent('Applying to project…');
  });

  it('does not describe an unchanged target as an interrupted applied run', () => {
    render(<DiffViewer files={[{ path: 'unchanged.py', language: 'python', additions: 0, deletions: 0, lines: [] }]}
      workspaceChanged sourceApplied phase="applied" />);
    expect(screen.getByRole('region', { name: 'Code diff' })).not.toHaveTextContent('ended before');
    expect(screen.getByText('No text hunks were recorded for this target.')).toBeInTheDocument();
  });
});
