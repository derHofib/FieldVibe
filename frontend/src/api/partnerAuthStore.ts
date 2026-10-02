export interface PartnerTokens {
  accessToken: string;
  refreshToken: string;
}

export const PARTNER_STORAGE_KEY = "fieldvibe_partnerportal_auth_v1";
type Listener = () => void;

function load(): PartnerTokens | null {
  try {
    const raw = localStorage.getItem(PARTNER_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PartnerTokens) : null;
  } catch {
    return null;
  }
}

let state: PartnerTokens | null = load();
const listeners = new Set<Listener>();

function persist() {
  try {
    if (state) localStorage.setItem(PARTNER_STORAGE_KEY, JSON.stringify(state));
    else localStorage.removeItem(PARTNER_STORAGE_KEY);
  } catch {
    /* Speicher gesperrt (z. B. privater Modus): Sitzung lebt dann nur im Speicher */
  }
  listeners.forEach((listener) => listener());
}

// Eigener Store (und eigener Storage-Key) statt authStore.ts/kundenAuthStore.ts:
// der Partner-Token hat einen eigenen Typ ("partner_access", siehe
// app/core/security.py) -- ein Mitarbeiter- oder Kunden-Token am Partner-
// Endpunkt (oder umgekehrt) waere eine Rechteausweitung bzw. liefe ins 401.
export const partnerAuthStore = {
  getState: (): PartnerTokens | null => state,

  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  setTokens(tokens: PartnerTokens | null) {
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
