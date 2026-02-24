// DECISION: Frontend queries Prompt Registry directly for autocomplete.
// Why: Autocomplete is a read-only operation that doesn't need agent involvement.
//   Querying the registry directly avoids round-tripping through the middleware.
// Production: Add authentication headers (JWT Bearer token).
// Alternative: Could proxy through middleware (adds latency, not needed for reads).

import type { Command, Skill } from '../types/commands';

const REGISTRY_URL = import.meta.env.VITE_REGISTRY_URL ?? 'http://localhost:8001';

export async function listCommands(search?: string): Promise<Command[]> {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  const res = await fetch(`${REGISTRY_URL}/api/v1/commands?${params}`);
  if (!res.ok) throw new Error(`Registry error: ${res.status}`);
  return res.json();
}

export async function listSkills(): Promise<Skill[]> {
  const res = await fetch(`${REGISTRY_URL}/api/v1/skills`);
  if (!res.ok) throw new Error(`Registry error: ${res.status}`);
  return res.json();
}

export async function getSkill(name: string): Promise<Skill | null> {
  const res = await fetch(`${REGISTRY_URL}/api/v1/skills/${name}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Registry error: ${res.status}`);
  return res.json();
}
