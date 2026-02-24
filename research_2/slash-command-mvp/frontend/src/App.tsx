import { ChatPanel } from './components/ChatPanel';
import { SkillCatalog } from './components/SkillCatalog';
import { useState } from 'react';

// DECISION: Direct REST+SSE instead of CopilotKit runtime.
// Why: CopilotKit 1.x runtime requires a LangGraph agent on the backend.
//   Our backend uses Pydantic AI, so a plain REST+SSE chat endpoint avoids
//   protocol mismatches and is simpler to debug.
// Production: Re-evaluate CopilotKit SDK or AG-UI protocol once agent framework
//   is standardised.

export default function App() {
  const [activeSkills, setActiveSkills] = useState<string[]>([]);

  function handleActivateSkill(skillName: string) {
    setActiveSkills(prev =>
      prev.includes(skillName) ? prev : [...prev, skillName]
    );
  }

  return (
    <div className="flex h-screen bg-gray-100">
      <div className="flex flex-col flex-1 overflow-hidden">
        <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-gray-900">Dev Assistant</h1>
            <p className="text-xs text-gray-500">Slash Command MVP — Pattern 2: Middleware Microservice</p>
          </div>
          {activeSkills.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Active skills:</span>
              {activeSkills.map(s => (
                <span key={s} className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full font-medium">
                  {s}
                </span>
              ))}
            </div>
          )}
        </header>

        <div className="flex flex-1 overflow-hidden">
          <main className="flex-1 overflow-hidden bg-white">
            <ChatPanel onActivateSkill={handleActivateSkill} />
          </main>
          <SkillCatalog onActivateSkill={handleActivateSkill} />
        </div>
      </div>
    </div>
  );
}
