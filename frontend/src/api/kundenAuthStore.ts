export interface KundenTokens {
  accessToken: string;
  refreshToken: string;
}

const STORAGE_KEY = "socialcrm_kundenportal_auth_v1";
type Listener = () => void;

function load(): KundenTokens | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as KundenTokens) : null;
  } catch {
    return null;
  }
}

let state: KundenTokens | null = load();
const listeners = new Set<Listener>();

function persist() {
  if (state) localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  else localStorage.removeItem(STORAGE_KEY);
  listeners.forEach((listener) => listener());
}

// Eigener Store statt Wiederverwendung von authStore.ts: das Kundenportal
// ist eine komplett getrennte Identitaet (siehe app/core/security.py,
// role="kunde"-Pseudorolle) -- ein separater Storage-Key verhindert, dass
// ein Kunden-Token je mit einem Staff-Token verwechselt oder ueberschrieben
// wird, selbst wenn beide Sessions im selben Browser offen sind.
export const kundenAuthStore = {
  getState: (): KundenTokens | null => state,

  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  setTokens(tokens: KundenTokens | null) {
    state = tokens;
    persist();
  },

  clear() {
    state = null;
    persist();
  },

  getAccessToken(): string | null {
    return state?.accessToken ?? null;
  },
};
