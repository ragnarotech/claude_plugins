// DECISION: Parameter form rendered client-side from variable definitions.
// Why: The registry returns typed variable schemas, so we can generate
//   appropriate form inputs (text, number, select) automatically.
// Production: Support complex schemas (conditional fields, file uploads, date pickers).
// Alternative: Always use text input (rejected: poor UX for select/enum variables).

import { useState } from 'react';
import type { Command, CommandVariable } from '../types/commands';

interface Props {
  command: Command;
  onSubmit: (args: Record<string, string>) => void;
  onDismiss: () => void;
}

export function ParamFormModal({ command, onSubmit, onDismiss }: Props) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const defaults: Record<string, string> = {};
    command.variables.forEach(v => {
      if (v.default) defaults[v.name] = v.default;
    });
    return defaults;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  function validate(): boolean {
    const newErrors: Record<string, string> = {};
    command.variables.forEach(v => {
      if (v.required && !values[v.name]) {
        newErrors[v.name] = `${v.name} is required`;
      }
    });
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (validate()) onSubmit(values);
  }

  function renderInput(variable: CommandVariable) {
    if (variable.type === 'select' && variable.enum) {
      return (
        <select
          className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={values[variable.name] ?? ''}
          onChange={e => setValues(prev => ({ ...prev, [variable.name]: e.target.value }))}
        >
          <option value="">Select...</option>
          {variable.enum.map(opt => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      );
    }
    return (
      <input
        type={variable.type === 'number' ? 'number' : 'text'}
        className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder={variable.description}
        value={values[variable.name] ?? ''}
        onChange={e => setValues(prev => ({ ...prev, [variable.name]: e.target.value }))}
        autoFocus
      />
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        <div className="bg-blue-600 text-white px-6 py-4">
          <h2 className="font-semibold text-lg">/{command.name}</h2>
          <p className="text-blue-100 text-sm mt-0.5">{command.description}</p>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {command.variables.map(variable => (
            <div key={variable.name}>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {variable.name}
                {variable.required && <span className="text-red-500 ml-1">*</span>}
              </label>
              <p className="text-xs text-gray-500 mb-1.5">{variable.description}</p>
              {renderInput(variable)}
              {errors[variable.name] && (
                <p className="text-xs text-red-500 mt-1">{errors[variable.name]}</p>
              )}
            </div>
          ))}
          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              className="flex-1 bg-blue-600 text-white rounded-lg py-2.5 text-sm font-semibold hover:bg-blue-700 transition-colors"
            >
              Run Command
            </button>
            <button
              type="button"
              onClick={onDismiss}
              className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
