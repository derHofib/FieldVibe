export interface Tokens {
  accessToken: string;
  refreshToken: string;
}

export interface ImpersonationSession {
  accessToken: string;
  mandantId: string;
  expiresInMinutes: number;
  startedAt: number;
}

interface AuthState {
  primary: Tokens | null;
  impersonation: ImpersonationSession | null;
}

const STORAGE_KEY = "fieldvibe_auth_v1";
type Listener = () => void;

function load(): AuthState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { primary: null, impersonation: null };
    return JSON.parse(raw) as AuthState;
  } catch {
    return { primary: null, impersonation: null };
  }
}

let state: AuthState = load();
const listeners = new Set<Listener>();

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  listeners.forEach((listener) => listener());
}

export const authStore = {
  getState: (): AuthState => state,

  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  setPrimary(tokens: Tokens | null) {
    state = { ...state, primary: tokens, impersonation: tokens ? state.impersonation : null };
    persist();
  },

  setImpersonation(session: ImpersonationSession | null) {
    state = { ...state, impersonation: session };
    persist();
  },

  clear() {
    state = { primary: null, impersonation: null };
    persist();
  },

  getActiveAccessToken(): string | null {
    return state.impersonation?.accessToken ?? state.primary?.accessToken ?? null;
  },

  isImpersonating(): boolean {
    return state.impersonation !== null;
  },
};
