// DECISION: Wrap CopilotKit's input with custom slash command detection.
// Why: CopilotKit doesn't have native slash command support. We intercept
//   at the message submission layer in this custom input component.
// Production: If CopilotKit adds native slash command support (#1925), migrate.
// COPILOTKIT: We use useCopilotChat's appendMessage for submitting commands.

import { useRef, KeyboardEvent } from 'react';
import { CommandPalette } from './CommandPalette';
import { ParamFormModal } from './ParamFormModal';
import { useSlashCommands } from '../hooks/useSlashCommands';

interface Props {
  onSendMessage: (message: string) => void;
  disabled?: boolean;
}

export function CommandInput({ onSendMessage, disabled }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const {
    inputValue, setInputValue,
    showPalette, filteredCommands, selectedIndex, setSelectedIndex,
    activeCommand, showParamForm,
    handleInputChange, handleSelectCommand, handleDismissPalette,
    handleParamFormSubmit, handleParamFormDismiss,
  } = useSlashCommands();

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (showPalette) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(Math.min(selectedIndex + 1, filteredCommands.length - 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(Math.max(selectedIndex - 1, 0));
        return;
      }
      if (e.key === 'Enter' && filteredCommands.length > 0) {
        e.preventDefault();
        handleSelectCommand(filteredCommands[selectedIndex]);
        return;
      }
      if (e.key === 'Escape') {
        handleDismissPalette();
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitMessage();
    }
  }

  function submitMessage() {
    const msg = inputValue.trim();
    if (!msg) return;
    setInputValue('');
    onSendMessage(msg);
  }

  function handleParamSubmit(args: Record<string, string>) {
    const msg = handleParamFormSubmit(args);
    if (msg) onSendMessage(msg);
  }

  return (
    <div className="relative">
      {showPalette && (
        <CommandPalette
          commands={filteredCommands}
          selectedIndex={selectedIndex}
          onSelect={handleSelectCommand}
          onDismiss={handleDismissPalette}
        />
      )}

      {showParamForm && activeCommand && (
        <ParamFormModal
          command={activeCommand}
          onSubmit={handleParamSubmit}
          onDismiss={handleParamFormDismiss}
        />
      )}

      <div className="flex gap-2 p-4 border-t border-gray-200 bg-white">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[52px] max-h-32"
            placeholder="Type a message or / for commands..."
            value={inputValue}
            onChange={e => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            rows={1}
          />
        </div>
        <button
          onClick={submitMessage}
          disabled={disabled || !inputValue.trim()}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors self-end"
        >
          Send
        </button>
      </div>
    </div>
  );
}
