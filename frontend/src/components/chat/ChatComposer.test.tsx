import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ChatComposer } from './ChatComposer';

const projectPath = '/tmp/calculadora demo';

describe('ChatComposer execution controls', () => {
  it('submits a functional specification without authorizing writes by default', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ChatComposer disabled={false} projectPath={projectPath} onSubmit={onSubmit} />);

    expect(screen.getByRole('radio', { name: /^dry run/i })).toBeChecked();
    await userEvent.type(screen.getByRole('textbox', { name: 'Task' }), '  Fix median  ');
    await userEvent.click(screen.getByRole('button', { name: /execute dry run/i }));

    expect(onSubmit).toHaveBeenCalledWith({ message: 'Fix median', testSpec: '', authorizeWrites: false });
  });

  it('sends the two specifications separately and writes only after explicit selection', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ChatComposer disabled={false} projectPath={projectPath} onSubmit={onSubmit} />);
    await userEvent.type(screen.getByRole('textbox', { name: 'Task' }), 'Fix median');
    await userEvent.type(screen.getByRole('textbox', { name: 'Test specification' }), '  Test even lengths  ');
    await userEvent.click(screen.getByRole('radio', { name: /authorize writes/i }));
    expect(screen.getByRole('note')).toHaveTextContent(projectPath);
    await userEvent.click(screen.getByRole('button', { name: /execute with writes/i }));

    expect(onSubmit).toHaveBeenCalledWith({
      message: 'Fix median', testSpec: 'Test even lengths', authorizeWrites: true,
    });
    expect(screen.getByRole('textbox', { name: 'Task' })).toHaveValue('');
    expect(screen.getByRole('textbox', { name: 'Test specification' })).toHaveValue('');
    expect(screen.getByRole('radio', { name: /^dry run/i })).toBeChecked();
  });

  it('does not carry write authorization to a different project', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(<ChatComposer disabled={false} projectPath={projectPath} onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole('radio', { name: /authorize writes/i }));

    rerender(<ChatComposer disabled={false} projectPath="C:\\projects\\another" onSubmit={onSubmit} />);

    expect(screen.getByRole('radio', { name: /^dry run/i })).toBeChecked();
  });

  it('keeps multiline Enter editing safe and supports Control+Enter submission', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ChatComposer disabled={false} projectPath={projectPath} onSubmit={onSubmit} />);
    await userEvent.type(screen.getByRole('textbox', { name: 'Task' }), 'Line one{Enter}Line two');
    expect(onSubmit).not.toHaveBeenCalled();

    await userEvent.keyboard('{Control>}{Enter}{/Control}');

    expect(onSubmit).toHaveBeenCalledWith({
      message: 'Line one\nLine two', testSpec: '', authorizeWrites: false,
    });
  });

  it('shows a launch failure without losing either specification', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('Backend is unavailable'));
    render(<ChatComposer disabled={false} projectPath={projectPath} onSubmit={onSubmit} />);
    await userEvent.type(screen.getByRole('textbox', { name: 'Task' }), 'Fix median');
    await userEvent.type(screen.getByRole('textbox', { name: 'Test specification' }), 'Test even lengths');
    await userEvent.click(screen.getByRole('radio', { name: /authorize writes/i }));
    await userEvent.click(screen.getByRole('button', { name: /execute with writes/i }));

    expect(screen.getByRole('alert')).toHaveTextContent('Backend is unavailable');
    expect(screen.getByRole('textbox', { name: 'Task' })).toHaveValue('Fix median');
    expect(screen.getByRole('textbox', { name: 'Test specification' })).toHaveValue('Test even lengths');
    expect(screen.getByRole('radio', { name: /^dry run/i })).toBeChecked();
  });

  it('prevents duplicate launches while a request is pending', async () => {
    let finish!: () => void;
    const onSubmit = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    render(<ChatComposer disabled={false} projectPath={projectPath} onSubmit={onSubmit} />);
    await userEvent.type(screen.getByRole('textbox', { name: 'Task' }), 'Fix median');
    const button = screen.getByRole('button', { name: /execute dry run/i });
    fireEvent.submit(button.closest('form')!);
    fireEvent.submit(button.closest('form')!);

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    finish();
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Task' })).toHaveValue(''));
  });

  it('disables both specifications and authorization without a selected project', () => {
    render(<ChatComposer disabled projectPath={null} onSubmit={vi.fn()} />);
    expect(screen.getByRole('textbox', { name: 'Task' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'Test specification' })).toBeDisabled();
    expect(screen.getByRole('radio', { name: /authorize writes/i })).toBeDisabled();
  });
});
