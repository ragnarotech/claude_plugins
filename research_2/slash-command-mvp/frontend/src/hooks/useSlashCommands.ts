// DECISION: useCopilotChat is the primary CopilotKit integration point.
// Why: CopilotKit doesn't have native slash command support (#1925 open issue).
//   We intercept at the message submission layer via this custom hook.
// Production: If CopilotKit adds native slash command support, migrate to that.
// Standard: Custom hook pattern follows React best practices.
// Alternative: Considered useCopilotAction (rejected: model-controlled, not user-controlled).

import { useState, useCallback, useRef } from 'react';
import { listCommands } from '../services/registryApi';
import type { Command } from '../types/commands';

interface UseSlashCommandsReturn {
  inputValue: string;
  setInputValue: (value: string) => void;
  showPalette: boolean;
  filteredCommands: Command[];
  selectedIndex: number;
  setSelectedIndex: (i: number) => void;
  activeCommand: Command | null;
  showParamForm: boolean;
  handleInputChange: (value: string) => void;
  handleSelectCommand: (command: Command) => void;
  handleDismissPalette: () => void;
  handleParamFormSubmit: (args: Record<string, string>) => string;
  handleParamFormDismiss: () => void;
  buildCommandMessage: (name: string, args: Record<string, string>) => string;
}

export function useSlashCommands(): UseSlashCommandsReturn {
  const [inputValue, setInputValue] = useState('');
  const [showPalette, setShowPalette] = useState(false);
  const [filteredCommands, setFilteredCommands] = useState<Command[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeCommand, setActiveCommand] = useState<Command | null>(null);
  const [showParamForm, setShowParamForm] = useState(false);
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleInputChange = useCallback((value: string) => {
    setInputValue(value);

    if (value.startsWith('/') && !value.includes(' ')) {
      // Searching for commands
      const searchTerm = value.slice(1); // Remove leading /
      setShowPalette(true);
      setSelectedIndex(0);

      // Debounce the search
      if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
      searchTimeoutRef.current = setTimeout(async () => {
        try {
          const commands = await listCommands(searchTerm || undefined);
          setFilteredCommands(commands);
        } catch (e) {
          console.error('Failed to fetch commands:', e);
          setFilteredCommands([]);
        }
      }, 150);
    } else {
      setShowPalette(false);
    }
  }, []);

  const handleSelectCommand = useCallback((command: Command) => {
    setShowPalette(false);
    setActiveCommand(command);

    // Check if command needs parameters
    const requiredVars = command.variables.filter(v => v.required);
    if (requiredVars.length > 0) {
      // Show parameter form
      setShowParamForm(true);
      setInputValue(`/${command.name} `);
    } else {
      // No params needed — set input to command string
      setInputValue(`/${command.name}`);
      setShowParamForm(false);
    }
  }, []);

  const handleDismissPalette = useCallback(() => {
    setShowPalette(false);
  }, []);

  const buildCommandMessage = useCallback((name: string, args: Record<string, string>): string => {
    // DECISION: Command submission sends raw "/command args" string to middleware.
    // Why: The middleware, not the frontend, resolves the template. This prevents
    //   template content (which may contain privileged context hints) from leaking to the client.
    // Alternative: Frontend could resolve the template directly (rejected: template leakage).
    const argValues = Object.values(args);
    const argsStr = argValues.map(v => v.includes(' ') ? `"${v}"` : v).join(' ');
    return argsStr ? `/${name} ${argsStr}` : `/${name}`;
  }, []);

  const handleParamFormSubmit = useCallback((args: Record<string, string>): string => {
    setShowParamForm(false);
    if (!activeCommand) return '';
    const msg = buildCommandMessage(activeCommand.name, args);
    setInputValue('');
    setActiveCommand(null);
    return msg;
  }, [activeCommand, buildCommandMessage]);

  const handleParamFormDismiss = useCallback(() => {
    setShowParamForm(false);
    setActiveCommand(null);
    setInputValue('');
  }, []);

  return {
    inputValue, setInputValue,
    showPalette, filteredCommands, selectedIndex, setSelectedIndex,
    activeCommand, showParamForm,
    handleInputChange, handleSelectCommand, handleDismissPalette,
    handleParamFormSubmit, handleParamFormDismiss, buildCommandMessage,
  };
}
