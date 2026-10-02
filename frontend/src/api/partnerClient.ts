import { ApiError } from "./client";
import { partnerAuthStore } from "./partnerAuthStore";
import type { TokenPair } from "../types";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 10000;

async function fetchWithTimeout(url: string, options: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

// Mehrere gleichzeitig 401-ende Requests (z. B. Liste + /me) sollen nur einen
// Refresh anstossen.
let laufenderRefresh: Promise<boolean> | null = null;

async function refreshToken(): Promise<boolean> {
  if (laufenderRefresh) return laufenderRefresh;
  const current = partnerAuthStore.getState();
  if (!current) return false;

  laufenderRefresh = (async () => {
    try {
      const resp = await fetchWithTimeout(`${BASE_URL}/api/partnerportal/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: current.refreshToken }),
      });
      if (!resp.ok) {
        // Nur bei klarer Ablehnung abmelden -- ein 5xx/Netzproblem auf der
        // Baustelle soll die Sitzung nicht wegwerfen.
        if (resp.status === 401 || resp.status === 403) partnerAuthStore.clear();
        return false;
      }
      const data = (await resp.json()) as TokenPair;
      partnerAuthStore.setTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
      return true;
    } catch {
      return false;
    } finally {
      laufenderRefresh = null;
    }
  })();
  return laufenderRefresh;
}

async function fehlerAus(resp: Response): Promise<ApiError> {
  let detail = resp.statusText;
  try {
    const body = await resp.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    /* Antwort ohne JSON-Body */
  }
  return new ApiError(resp.status, detail);
}

export async function partnerApiFetch<T>(
  path: string,
  options: RequestInit = {},
  _isRetry = false,
): Promise<T> {
  const token = partnerAuthStore.getAccessToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetchWithTimeout(`${BASE_URL}${path}`, { ...options, headers });

  // Login/Registrierung/Reset liefern 401 fuer "falsche Daten", nicht fuer
  // "Token abgelaufen" -- dort weder refreshen noch abmelden.
  const istAuthPfad = path.startsWith("/api/partnerportal/auth/") && path !== "/api/partnerportal/auth/me";
  if (resp.status === 401 && token && !istAuthPfad) {
    if (!_isRetry && (await refreshToken())) {
      return partnerApiFetch<T>(path, options, true);
    }
    // Refresh gescheitert oder frischer Token trotzdem abgelehnt: Sitzung beenden.
    if (_isRetry) partnerAuthStore.clear();
  }

  if (!resp.ok) throw await fehlerAus(resp);

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}
