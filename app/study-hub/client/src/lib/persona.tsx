import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type Persona = 'study_manager' | 'admin';

export const PERSONA_LABEL: Record<Persona, string> = {
  study_manager: 'Study Manager',
  admin: 'Admin (Approver)',
};

interface PersonaContextValue {
  persona: Persona;
  setPersona: (p: Persona) => void;
  email: string | null;
  apiFetch: (input: string, init?: RequestInit) => Promise<Response>;
}

const PersonaContext = createContext<PersonaContextValue | null>(null);
const STORAGE_KEY = 'study-hub:persona';

export function PersonaProvider({ children }: { children: ReactNode }) {
  const [persona, setPersonaState] = useState<Persona>(() =>
    localStorage.getItem(STORAGE_KEY) === 'admin' ? 'admin' : 'study_manager',
  );
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/whoami')
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { email?: string | null } | null) => setEmail(d?.email ?? null))
      .catch(() => setEmail(null));
  }, []);

  const setPersona = useCallback((p: Persona) => {
    localStorage.setItem(STORAGE_KEY, p);
    setPersonaState(p);
  }, []);

  const apiFetch = useCallback(
    (input: string, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      headers.set('x-demo-persona', persona);
      if (init?.body && typeof init.body === 'string') headers.set('Content-Type', 'application/json');
      return fetch(input, { ...init, headers });
    },
    [persona],
  );

  const value = useMemo(() => ({ persona, setPersona, email, apiFetch }), [persona, setPersona, email, apiFetch]);
  return <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>;
}

export function usePersona(): PersonaContextValue {
  const ctx = useContext(PersonaContext);
  if (!ctx) throw new Error('usePersona must be used inside PersonaProvider');
  return ctx;
}
