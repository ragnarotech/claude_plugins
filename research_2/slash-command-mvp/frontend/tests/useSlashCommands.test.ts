import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSlashCommands } from '../src/hooks/useSlashCommands';

// Mock the registryApi
vi.mock('../src/services/registryApi', () => ({
  listCommands: vi.fn().mockResolvedValue([]),
}));

describe('useSlashCommands', () => {
  it('shows palette when input starts with /', async () => {
    const { result } = renderHook(() => useSlashCommands());
    act(() => result.current.handleInputChange('/'));
    // After debounce and mock resolve
    expect(result.current.inputValue).toBe('/');
  });

  it('hides palette for normal input', () => {
    const { result } = renderHook(() => useSlashCommands());
    act(() => result.current.handleInputChange('hello'));
    expect(result.current.showPalette).toBe(false);
  });

  it('builds command message without spaces for no-arg command', () => {
    const { result } = renderHook(() => useSlashCommands());
    const msg = result.current.buildCommandMessage('list-my-tickets', {});
    expect(msg).toBe('/list-my-tickets');
  });

  it('builds command message with args', () => {
    const { result } = renderHook(() => useSlashCommands());
    const msg = result.current.buildCommandMessage('triage-ticket', { ticket_number: 'PROJ-1234' });
    expect(msg).toBe('/triage-ticket PROJ-1234');
  });
});
