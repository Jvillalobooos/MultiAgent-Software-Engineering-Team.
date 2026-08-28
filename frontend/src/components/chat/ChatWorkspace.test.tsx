import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ChatWorkspace } from './ChatWorkspace';
import { FakeRunClient, approvedFixture } from '../../test/FakeRunClient';
import { ApplyResult, RunSnapshot } from '../../types/mission';

describe('ChatWorkspace', () => {
  it('displays the persisted test specification and write permission on the run', async () => {
    const snapshot = approvedFixture();
    snapshot.test_spec = 'Check median([7, 8, 9, 10]) equals 8.5';
    snapshot.authorize_writes = true;
    const client = new FakeRunClient(snapshot);
    client.listRuns = vi.fn().mockResolvedValue([snapshot]);
    render(<ChatWorkspace client={client} />);
    await userEvent.click(await screen.findByRole('button', { name: /open run: change it/i }));
    expect(await screen.findByLabelText('Run write permission')).toHaveTextContent('Writes authorized');
    await userEvent.click(screen.getByText('Test specification', { selector: 'summary' }));
    expect(screen.getByText(snapshot.test_spec)).toBeVisible();
  });

  it('shows retained project changes after failed source verification', async () => {
    const snapshot = approvedFixture();
    snapshot.phase = 'apply_failed';
    snapshot.apply_result = {
      status: 'apply_failed', written_paths: ['app.py'], test_exit_code: 1,
      backup_path: 'backup', test_output: '1 failed', message: 'Verification failed',
    };
    const client = new FakeRunClient(snapshot);
    client.listRuns = vi.fn().mockResolvedValue([snapshot]);
    render(<ChatWorkspace client={client} />);
    await userEvent.click(await screen.findByRole('button', { name: /open run: change it/i }));
    expect(await screen.findByRole('region', { name: 'Code diff' })).toHaveTextContent('Verification failed · project changes retained');
  });

  it('launches from a manually selected project with separate test expectations and explicit permission', async () => {
    const client = new FakeRunClient();
    client.selectProject = vi.fn().mockResolvedValue({
      status: 'selected', project: { path: '/private/tmp/calculadora demo', name: 'calculadora demo' },
    });
    render(<ChatWorkspace client={client} />);
    await userEvent.click(screen.getByRole('button', { name: /enter path/i }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Project folder path' }), '/tmp/calculadora demo');
    await userEvent.click(screen.getByRole('button', { name: /use folder/i }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Task' }), 'Fix median');
    await userEvent.type(screen.getByRole('textbox', { name: 'Test specification' }), 'Cover even-length lists');
    await userEvent.click(screen.getByRole('radio', { name: /authorize writes/i }));
    await userEvent.click(screen.getByRole('button', { name: /execute with writes/i }));

    expect(client.requests).toEqual([{
      projectPath: '/private/tmp/calculadora demo', message: 'Fix median',
      testSpec: 'Cover even-length lists', authorizeWrites: true,
    }]);
  });

  it('creates independent runs with only the current message', async () => {
    const client = new FakeRunClient();
    render(<ChatWorkspace client={client} />);

    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));
    await userEvent.type(screen.getByRole('textbox', { name: /task/i }), 'first change');
    await userEvent.click(screen.getByRole('button', { name: /execute/i }));
    await userEvent.type(screen.getByRole('textbox', { name: /task/i }), 'second change');
    await userEvent.click(screen.getByRole('button', { name: /execute/i }));

    await waitFor(() =>
      expect(client.requests).toEqual([
        { projectPath: 'C:\\projects\\calculator', message: 'first change', authorizeWrites: false },
        { projectPath: 'C:\\projects\\calculator', message: 'second change', authorizeWrites: false },
      ])
    );
    // Only the run just launched is mounted; the earlier one is history, not a card.
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(screen.getByTestId('run-trace-id')).toHaveTextContent('run-2');
    // Both runs are still reachable as separate history entries.
    await userEvent.click(screen.getByRole('button', { name: /back to history/i }));
    expect(screen.getByRole('region', { name: 'Run history' })).toHaveTextContent('2 executions');
    expect(screen.getByRole('button', { name: /open run: first change/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /open run: second change/i })).toBeInTheDocument();
  });

  it('opens on the launch screen and lists stored runs as history instead of mounting them', async () => {
    const client = new FakeRunClient();
    client.listRuns = vi.fn().mockResolvedValue([
      { ...approvedFixture(), run_id: 'run-old', message: 'an earlier change' },
    ]);
    render(<ChatWorkspace client={client} />);

    expect(await screen.findByRole('region', { name: 'Run history' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Start a run' })).toBeInTheDocument();
    // Restarting the backend must not replay stored runs into the viewport.
    expect(screen.queryByRole('article')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /open run: an earlier change/i }));
    expect(await screen.findByRole('article')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /back to history/i }));
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });

  it('filters history by instruction and by project, and says so when nothing matches', async () => {
    const base = approvedFixture();
    const client = new FakeRunClient();
    client.listRuns = vi.fn().mockResolvedValue([
      { ...base, run_id: 'r1', message: 'fix the median', project_path: 'C:\\projects\\calculator' },
      { ...base, run_id: 'r2', message: 'add a parser', project_path: 'C:\\projects\\invoices' },
    ]);
    render(<ChatWorkspace client={client} />);

    const filter = await screen.findByRole('searchbox', { name: /filter runs/i });
    await userEvent.type(filter, 'median');
    expect(screen.getByRole('button', { name: /open run: fix the median/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /open run: add a parser/i })).not.toBeInTheDocument();

    // The project path is searchable too, not just the instruction.
    await userEvent.clear(filter);
    await userEvent.type(filter, 'invoices');
    expect(screen.getByRole('button', { name: /open run: add a parser/i })).toBeInTheDocument();

    await userEvent.clear(filter);
    await userEvent.type(filter, 'nothing matches this');
    expect(screen.getByText(/no run matches/i)).toBeInTheDocument();
  });

  it('reuses a past instruction by refilling the composer without launching a run', async () => {
    const base = approvedFixture();
    const client = new FakeRunClient();
    client.listRuns = vi.fn().mockResolvedValue([
      { ...base, run_id: 'r1', message: 'fix the median', test_spec: 'cover even-length lists' },
    ]);
    render(<ChatWorkspace client={client} />);

    await userEvent.click(await screen.findByRole('button', { name: /reuse this instruction/i }));

    expect(screen.getByRole('textbox', { name: 'Task' })).toHaveValue('fix the median');
    expect(screen.getByRole('textbox', { name: 'Test specification' })).toHaveValue('cover even-length lists');
    // Reuse prepares a run; it must never spend provider quota on its own.
    expect(client.requests).toEqual([]);
    // Write permission is never inherited from the run being reused.
    expect(screen.getByRole('radio', { name: /dry run/i })).toBeChecked();
  });

  it('leaves an open run on Escape and returns to history', async () => {
    const client = new FakeRunClient();
    render(<ChatWorkspace client={client} />);
    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));
    await userEvent.type(screen.getByRole('textbox', { name: /task/i }), 'change it');
    await userEvent.click(screen.getByRole('button', { name: /execute/i }));
    await waitFor(() => expect(screen.getByRole('article')).toBeInTheDocument());

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Run history' })).toBeInTheDocument();
  });

  it('explains what the current phase obliges the operator to do', async () => {
    const client = new FakeRunClient({ ...approvedFixture(), phase: 'review_required' });
    client.listRuns = vi.fn().mockResolvedValue([{ ...approvedFixture(), phase: 'review_required' }]);
    render(<ChatWorkspace client={client} />);
    await userEvent.click(await screen.findByRole('button', { name: /open run: change it/i }));

    expect(await screen.findByText(/the reviewer did not approve/i)).toBeInTheDocument();
  });

  it('collapses retries of the same instruction on the same project into one history entry', async () => {
    const base = approvedFixture();
    const client = new FakeRunClient();
    client.listRuns = vi.fn().mockResolvedValue([
      { ...base, run_id: 'run-3', message: 'fix median', phase: 'approved', created_at: '2026-08-27T10:02:00-06:00' },
      { ...base, run_id: 'run-2', message: 'fix median', phase: 'failed', created_at: '2026-08-27T10:01:00-06:00' },
      { ...base, run_id: 'run-1', message: 'fix median', phase: 'failed', created_at: '2026-08-27T10:00:00-06:00' },
      { ...base, run_id: 'run-other', message: 'unrelated change', created_at: '2026-08-27T09:00:00-06:00' },
    ]);
    render(<ChatWorkspace client={client} />);

    const history = await screen.findByRole('region', { name: 'Run history' });
    expect(history).toHaveTextContent('2 executions');
    // The three attempts collapse behind one row, expandable to reach each attempt.
    const attempts = screen.getByRole('button', { name: /3 attempts of this run/i });
    expect(attempts).toHaveTextContent('×3');

    await userEvent.click(attempts);
    expect(screen.getByRole('button', { name: /attempt 2/i })).toBeInTheDocument();
  });

  it('does not select a project when the native picker is cancelled', async () => {
    const client = new FakeRunClient();
    client.pickProject = vi.fn().mockResolvedValue({ status: 'cancelled', project: null });
    render(<ChatWorkspace client={client} />);

    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));

    expect(screen.getByRole('textbox', { name: /task/i })).toBeDisabled();
  });

  it('leaves the composer disabled with no project and re-enables once selected', async () => {
    const client = new FakeRunClient();
    render(<ChatWorkspace client={client} />);

    expect(screen.getByRole('textbox', { name: /task/i })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));
    await waitFor(() => expect(screen.getByRole('textbox', { name: /task/i })).toBeEnabled());
  });

  it('shows apply confirmation naming the project and affected paths, and relabels on success', async () => {
    const client = new FakeRunClient();
    render(<ChatWorkspace client={client} />);
    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));
    await userEvent.type(screen.getByRole('textbox', { name: /task/i }), 'change it');
    await userEvent.click(screen.getByRole('button', { name: /execute/i }));

    await waitFor(() => expect(screen.getByRole('button', { name: /^apply$/i })).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /^apply$/i }));

    const confirmation = screen.getByRole('group', { name: /confirm apply/i });
    expect(confirmation).toHaveTextContent('C:\\projects\\calculator');
    expect(confirmation).toHaveTextContent('app.py');

    await userEvent.click(screen.getByRole('button', { name: /confirm apply/i }));

    await waitFor(() => expect(screen.getByTestId('run-phase-badge')).toHaveTextContent(/applied/i));
    expect(screen.getByRole('region', { name: /apply result/i })).toHaveTextContent('app.py');
    expect(screen.getByRole('region', { name: /apply result/i })).toHaveTextContent('1 passed');
    expect(screen.queryByRole('button', { name: /^apply$/i })).not.toBeInTheDocument();
  });

  it('leaves the card approved with a visible conflict message on apply conflict', async () => {
    const client = new FakeRunClient();
    client.apply = vi.fn().mockResolvedValue({
      status: 'conflict', written_paths: [], test_exit_code: null,
      test_output: '', backup_path: null, message: 'Workspace changed since approval',
    } satisfies ApplyResult);
    render(<ChatWorkspace client={client} />);
    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));
    await userEvent.type(screen.getByRole('textbox', { name: /task/i }), 'change it');
    await userEvent.click(screen.getByRole('button', { name: /execute/i }));

    await waitFor(() => expect(screen.getByRole('button', { name: /^apply$/i })).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /^apply$/i }));
    await userEvent.click(screen.getByRole('button', { name: /confirm apply/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/workspace changed since approval/i));
    expect(screen.getByRole('article')).toHaveTextContent('Approved');
  });

  it('renders the persisted apply result from a reloaded snapshot with no apply ever called', async () => {
    const client = new FakeRunClient({
      ...approvedFixture(),
      phase: 'applied',
      apply_result: {
        status: 'applied', written_paths: ['app.py', 'app2.py'], test_exit_code: 0,
        test_output: 'reloaded test output', backup_path: 'C:\\runs\\run-a\\backup',
        message: 'applied successfully',
      },
    });
    render(<ChatWorkspace client={client} />);
    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));
    await userEvent.type(screen.getByRole('textbox', { name: /task/i }), 'change it');
    await userEvent.click(screen.getByRole('button', { name: /execute/i }));

    await waitFor(() => expect(screen.getByTestId('run-phase-badge')).toHaveTextContent(/applied/i));
    const section = screen.getByRole('region', { name: /apply result/i });
    expect(section).toHaveTextContent('app.py, app2.py');
    expect(section).toHaveTextContent('reloaded test output');
    expect(section).toHaveTextContent('available');
    expect(screen.queryByRole('button', { name: /^apply$/i })).not.toBeInTheDocument();
  });

  it('never renders a run as Failed because of a cloud-fallback warning event', async () => {
    const client = new FakeRunClient();
    const withWarning: RunSnapshot = {
      ...approvedFixture(),
      phase: 'running',
      report: null,
      events: [{
        sequence: 1,
        payload: {
          id: 'e1', name: 'Cloud fallback', type: 'error', level: 'warn',
          status_message: 'Falling back to cloud provider', metadata: {},
          agent: 'developer', iteration: 0, at: 1,
        },
      }],
    };
    client.snapshot = withWarning;
    render(<ChatWorkspace client={client} />);
    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));
    await userEvent.type(screen.getByRole('textbox', { name: /task/i }), 'change it');
    await userEvent.click(screen.getByRole('button', { name: /execute/i }));

    await waitFor(() => expect(screen.getByText(/agents working/i)).toBeInTheDocument());
    expect(screen.queryByText(/^failed$/i)).not.toBeInTheDocument();
  });
});
