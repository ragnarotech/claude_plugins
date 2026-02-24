// DECISION: Skill catalog is a simple list for MVP.
// Why: Skills are browseable context — users should be able to see what
//   capabilities are available and activate them explicitly.
// Production: Categorized, searchable, with usage analytics and ratings.
// Standard: Follows Agent Skills format (SKILL.md + frontmatter metadata).

import { useSkills } from '../hooks/useSkills';
import type { Skill } from '../types/commands';

interface Props {
  onActivateSkill: (skillName: string) => void;
}

export function SkillCatalog({ onActivateSkill }: Props) {
  const { skills, loading, error } = useSkills();

  return (
    <div className="w-64 bg-gray-50 border-l border-gray-200 flex flex-col">
      <div className="px-4 py-3 border-b border-gray-200 bg-white">
        <h2 className="font-semibold text-gray-800 text-sm">Agent Skills</h2>
        <p className="text-xs text-gray-500 mt-0.5">Activate to enhance responses</p>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {loading && (
          <p className="text-xs text-gray-500 text-center py-4">Loading skills...</p>
        )}
        {error && (
          <p className="text-xs text-red-500 text-center py-4">Failed to load skills</p>
        )}
        {skills.map(skill => (
          <SkillCard key={skill.id} skill={skill} onActivate={onActivateSkill} />
        ))}
        {!loading && skills.length === 0 && (
          <p className="text-xs text-gray-500 text-center py-4">No skills available</p>
        )}
      </div>

      <div className="px-4 py-3 border-t border-gray-200 bg-white">
        <p className="text-xs text-gray-400">
          Or type <code className="bg-gray-100 px-1 rounded">/use-skill &lt;name&gt;</code> in chat
        </p>
      </div>
    </div>
  );
}

function SkillCard({ skill, onActivate }: { skill: Skill; onActivate: (name: string) => void }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3 hover:border-blue-300 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-sm text-gray-800">{skill.name}</h3>
          <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{skill.description}</p>
        </div>
      </div>
      {skill.tools.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {skill.tools.map(tool => (
            <span key={tool} className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded font-mono">
              {tool}
            </span>
          ))}
        </div>
      )}
      <button
        onClick={() => onActivate(skill.name)}
        className="mt-2 w-full text-xs bg-blue-600 text-white rounded py-1.5 hover:bg-blue-700 transition-colors font-medium"
      >
        Activate Skill
      </button>
    </div>
  );
}
