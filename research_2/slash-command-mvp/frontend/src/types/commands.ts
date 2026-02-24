export interface CommandVariable {
  name: string;
  type: 'string' | 'number' | 'select';
  required: boolean;
  description: string;
  default?: string;
  enum?: string[];
}

export interface Command {
  id: string;
  name: string;
  display_name: string;
  description: string;
  template: string;
  variables: CommandVariable[];
  tools: string[];
  tags: string[];
  source: 'builtin' | 'user' | 'marketplace';
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  skill_md: string;
  frontmatter: Record<string, unknown>;
  tools: string[];
  tags: string[];
  source: string;
  is_active: boolean;
}

export interface ResolvedCommand {
  command_name: string;
  resolved_prompt: string;
  system_context: string;
  required_tools: string[];
  original_command: string;
  metadata: Record<string, unknown>;
}
