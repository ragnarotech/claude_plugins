// DECISION: CommandPalette positioned above chat input, like Discord/Slack.
// Why: This is the established UX pattern users expect for slash commands.
// Production: Add command categories, usage count, keyboard shortcut hints.
// Alternative: Inline autocomplete (rejected: harder to show full descriptions).

import type { Command } from '../types/commands';

interface Props {
  commands: Command[];
  selectedIndex: number;
  onSelect: (command: Command) => void;
  onDismiss: () => void;
}

export function CommandPalette({ commands, selectedIndex, onSelect }: Props) {
  if (commands.length === 0) return null;

  return (
    <div className="absolute bottom-full mb-2 left-0 right-0 bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden z-50">
      <div className="px-3 py-2 bg-gray-50 border-b text-xs text-gray-500 font-medium">
        SLASH COMMANDS — Select with &#x2191;&#x2193; Enter, dismiss with Esc
      </div>
      <ul className="max-h-64 overflow-y-auto">
        {commands.map((cmd, i) => (
          <li
            key={cmd.id}
            className={`px-4 py-3 cursor-pointer hover:bg-blue-50 ${i === selectedIndex ? 'bg-blue-50 border-l-2 border-blue-500' : ''}`}
            onClick={() => onSelect(cmd)}
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-semibold text-blue-700">/{cmd.name}</span>
              {cmd.variables.length > 0 && (
                <span className="text-xs text-gray-400">
                  {cmd.variables.filter(v => v.required).map(v => `<${v.name}>`).join(' ')}
                </span>
              )}
              <span className="ml-auto text-xs text-gray-400 capitalize">{cmd.source}</span>
            </div>
            <p className="text-xs text-gray-600 mt-0.5">{cmd.description}</p>
            {cmd.tags.length > 0 && (
              <div className="flex gap-1 mt-1">
                {cmd.tags.slice(0, 3).map(tag => (
                  <span key={tag} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
