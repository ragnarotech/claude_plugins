import { useState, useEffect } from 'react';
import { listSkills } from '../services/registryApi';
import type { Skill } from '../types/commands';

export function useSkills() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSkills()
      .then(setSkills)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return { skills, loading, error };
}
