import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { CommandPalette } from '../src/components/CommandPalette';
import type { Command } from '../src/types/commands';

const mockCommands: Command[] = [
  {
    id: '1',
    name: 'triage-ticket',
    display_name: 'Triage Ticket',
    description: 'Triage a Jira ticket',
    variables: [{ name: 'ticket_number', type: 'string', required: true, description: 'Ticket number' }],
    tools: [],
    tags: ['jira'],
    source: 'builtin',
    version: 1,
    is_active: true,
    created_at: '',
    updated_at: '',
    template: '',
  },
  {
    id: '2',
    name: 'list-my-tickets',
    display_name: 'List My Tickets',
    description: 'List tickets',
    variables: [],
    tools: [],
    tags: [],
    source: 'builtin',
    version: 1,
    is_active: true,
    created_at: '',
    updated_at: '',
    template: '',
  },
];

describe('CommandPalette', () => {
  it('renders command list', () => {
    render(<CommandPalette commands={mockCommands} selectedIndex={0} onSelect={vi.fn()} onDismiss={vi.fn()} />);
    expect(screen.getByText('/triage-ticket')).toBeInTheDocument();
    expect(screen.getByText('/list-my-tickets')).toBeInTheDocument();
  });

  it('highlights selected command', () => {
    const { container } = render(<CommandPalette commands={mockCommands} selectedIndex={1} onSelect={vi.fn()} onDismiss={vi.fn()} />);
    const items = container.querySelectorAll('li');
    expect(items[1].className).toContain('border-blue-500');
  });

  it('calls onSelect when command clicked', () => {
    const onSelect = vi.fn();
    render(<CommandPalette commands={mockCommands} selectedIndex={0} onSelect={onSelect} onDismiss={vi.fn()} />);
    fireEvent.click(screen.getByText('/triage-ticket').closest('li')!);
    expect(onSelect).toHaveBeenCalledWith(mockCommands[0]);
  });

  it('returns null for empty commands', () => {
    const { container } = render(<CommandPalette commands={[]} selectedIndex={0} onSelect={vi.fn()} onDismiss={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });
});
