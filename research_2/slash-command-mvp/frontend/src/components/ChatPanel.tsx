// DECISION: Direct REST+SSE chat instead of CopilotKit runtime.
// Why: Eliminates CopilotKit protocol dependency. The backend streams SSE
//   events (message_start, message_delta, message_end, done) which we
//   consume with a standard ReadableStream reader.
// Production: Adopt a proper AG-UI protocol client or CopilotKit SDK once
//   the backend uses a compatible agent framework.

import { useState, useRef, useEffect } from 'react';
import { CommandInput } from './CommandInput';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

interface Props {
  onActivateSkill: (skillName: string) => void;
}

export function ChatPanel({ onActivateSkill }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  async function handleSendMessage(content: string) {
    // Skill activation shortcut
    if (content.startsWith('/use-skill ')) {
      const skillName = content.replace('/use-skill ', '').trim();
      onActivateSkill(skillName);
    }

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setIsLoading(true);

    try {
      const resp = await fetch(`${API_URL}/api/v1/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: updatedMessages.map(m => ({ role: m.role, content: m.content })),
        }),
      });

      if (!resp.ok || !resp.body) {
        const errText = await resp.text();
        setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: `Error: ${errText}` }]);
        return;
      }

      // Parse SSE stream
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let assistantId = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        // Keep the last potentially incomplete line
        buffer = lines.pop() ?? '';

        let currentEvent = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7);
          } else if (line.startsWith('data: ') && currentEvent) {
            const data = JSON.parse(line.slice(6));

            if (currentEvent === 'message_start') {
              assistantId = data.messageId;
              setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '' }]);
            } else if (currentEvent === 'message_delta') {
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, content: m.content + data.delta } : m)
              );
            }
            // message_end and done need no special handling
            currentEvent = '';
          }
        }
      }
    } catch (err) {
      setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: `Connection error: ${err}` }]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-12">
            <p className="text-lg font-medium">Hello! I can help with Jira tickets, PRs, and code reviews.</p>
            <p className="text-sm mt-1">Type <code className="bg-gray-100 px-1 rounded">/</code> to see available commands.</p>
          </div>
        )}
        {messages.map(msg => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[75%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              {msg.content || (isLoading ? '...' : '')}
            </div>
          </div>
        ))}
      </div>
      <CommandInput onSendMessage={handleSendMessage} disabled={isLoading} />
    </div>
  );
}
