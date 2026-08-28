import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { FakeRunClient } from '../../test/FakeRunClient';
import { ProjectPickResponse } from '../../types/mission';
import { ProjectHeader } from './ProjectHeader';

describe('ProjectHeader folder selection', () => {
  it.each(['/tmp/proyecto con espacios', 'C:\\Proyectos\\Cálculo'])('validates the typed path through the backend: %s', async (path) => {
    const client = new FakeRunClient();
    const project = { path, name: 'Cálculo' };
    client.selectProject = vi.fn().mockResolvedValue({ status: 'selected', project });
    const onProjectSelected = vi.fn();
    render(<ProjectHeader client={client} selectedProject={null} onProjectSelected={onProjectSelected} />);
    await userEvent.click(screen.getByRole('button', { name: /enter path/i }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Project folder path' }), `  ${path}  `);
    await userEvent.click(screen.getByRole('button', { name: /use folder/i }));

    expect(client.selectProject).toHaveBeenCalledWith(path);
    expect(onProjectSelected).toHaveBeenCalledWith(project);
  });

  it('offers manual entry and a visible error after native selection fails', async () => {
    const client = new FakeRunClient();
    client.pickProject = vi.fn().mockRejectedValue(new Error('System folder dialog unavailable'));
    render(<ProjectHeader client={client} selectedProject={null} onProjectSelected={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));

    expect(screen.getByRole('alert')).toHaveTextContent('System folder dialog unavailable');
    expect(screen.getByRole('textbox', { name: 'Project folder path' })).toBeEnabled();
    expect(screen.getByRole('button', { name: /select folder/i })).toBeEnabled();
  });

  it('preserves the current project when the native dialog is cancelled', async () => {
    const client = new FakeRunClient();
    client.pickProject = vi.fn().mockResolvedValue({ status: 'cancelled', project: null });
    const onProjectSelected = vi.fn();
    render(<ProjectHeader client={client} selectedProject={{ path: '/tmp/current', name: 'current' }} onProjectSelected={onProjectSelected} />);
    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));

    expect(onProjectSelected).not.toHaveBeenCalled();
    expect(screen.getByText(/\/tmp\/current/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('leaves an invalid path editable and displays the validation failure', async () => {
    const client = new FakeRunClient();
    client.selectProject = vi.fn().mockRejectedValue(new Error('Project folder does not exist'));
    const onProjectSelected = vi.fn();
    render(<ProjectHeader client={client} selectedProject={null} onProjectSelected={onProjectSelected} />);
    await userEvent.click(screen.getByRole('button', { name: /enter path/i }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Project folder path' }), '/tmp/missing');
    await userEvent.click(screen.getByRole('button', { name: /use folder/i }));

    expect(screen.getByRole('alert')).toHaveTextContent('Project folder does not exist');
    expect(screen.getByRole('textbox', { name: 'Project folder path' })).toHaveValue('/tmp/missing');
    expect(onProjectSelected).not.toHaveBeenCalled();
  });

  it('does not let a late native selection replace a newer manual selection', async () => {
    const client = new FakeRunClient();
    let finishPicker!: (response: ProjectPickResponse) => void;
    client.pickProject = vi.fn(() => new Promise<ProjectPickResponse>((resolve) => { finishPicker = resolve; }));
    const manual = { path: '/tmp/manual', name: 'manual' };
    client.selectProject = vi.fn().mockResolvedValue({ status: 'selected', project: manual });
    const onProjectSelected = vi.fn();
    render(<ProjectHeader client={client} selectedProject={null} onProjectSelected={onProjectSelected} />);
    await userEvent.click(screen.getByRole('button', { name: /select folder/i }));
    await userEvent.click(screen.getByRole('button', { name: /enter path/i }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Project folder path' }), manual.path);
    await userEvent.click(screen.getByRole('button', { name: /use folder/i }));
    await act(async () => finishPicker({ status: 'selected', project: { path: '/tmp/old', name: 'old' } }));

    await waitFor(() => expect(screen.getByRole('button', { name: /select folder/i })).toBeEnabled());
    expect(onProjectSelected).toHaveBeenCalledTimes(1);
    expect(onProjectSelected).toHaveBeenCalledWith(manual);
  });
});
