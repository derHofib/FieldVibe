import { authStore } from "./authStore";
import type { TokenPair } from "../types";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// A request out in the field can stall indefinitely on a degrading signal
// (fetch() gives no built-in ceiling), which would otherwise hang mutations
// forever instead of falling back to the offline outbox. This bounds every
// request so a stuck connection surfaces as a normal (retriable) failure.
const REQUEST_TIMEOUT_MS = 10000;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// FastAPI liefert bei 422 (Pydantic-Validierung) `detail` als ARRAY von
// {loc, msg, type}-Objekten statt eines Strings -- das `typeof === "string"`-
// Pruefung darunter griff dafuer nie, jeder 422-Fehler fiel deshalb bislang
// auf resp.statusText ("Unprocessable Entity") zurueck, egal wie aussage-
// kraeftig die eigentliche Meldung (z.B. ein model_validator-ValueError)
// gewesen waere.
function extractErrorDetail(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail
      .map((d) => {
        if (!d || typeof d !== "object") return null;
        const msgRaw = (d as { msg?: unknown }).msg;
        if (typeof msgRaw !== "string") return null;
        const msg = msgRaw.replace(/^Value error,\s*/, "");
        const loc = (d as { loc?: unknown }).loc;
        const feld = Array.isArray(loc) ? loc.filter((l) => l !== "body").pop() : null;
        return typeof feld === "string" ? `${feld}: ${msg}` : msg;
      })
      .filter((m): m is string => !!m);
    if (messages.length > 0) return messages.join("; ");
  }
  return null;
}

async function fetchWithTimeout(url: string, options: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

async function refreshPrimaryToken(): Promise<boolean> {
  const primary = authStore.getState().primary;
  if (!primary) return false;

  const resp = await fetchWithTimeout(`${BASE_URL}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: primary.refreshToken }),
  });
  if (!resp.ok) {
    authStore.clear();
    return false;
  }
  const data = (await resp.json()) as TokenPair;
  authStore.setPrimary({ accessToken: data.access_token, refreshToken: data.refresh_token });
  return true;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  _isRetry = false,
): Promise<T> {
  const token = authStore.getActiveAccessToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetchWithTimeout(`${BASE_URL}${path}`, { ...options, headers });

  if (resp.status === 401 && !_isRetry) {
    if (authStore.isImpersonating()) {
      authStore.setImpersonation(null);
      return apiFetch<T>(path, options, true);
    }
    if (await refreshPrimaryToken()) {
      return apiFetch<T>(path, options, true);
    }
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = extractErrorDetail(body) ?? detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

/** Like apiFetch, but for multipart/form-data (file uploads): the browser
 * must set its own Content-Type with the multipart boundary, so this must
 * NOT set one explicitly the way apiFetch does for JSON. */
export async function apiFetchForm<T>(
  path: string,
  formData: FormData,
  _isRetry = false,
): Promise<T> {
  const token = authStore.getActiveAccessToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetchWithTimeout(`${BASE_URL}${path}`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (resp.status === 401 && !_isRetry) {
    if (authStore.isImpersonating()) {
      authStore.setImpersonation(null);
      return apiFetchForm<T>(path, formData, true);
    }
    if (await refreshPrimaryToken()) {
      return apiFetchForm<T>(path, formData, true);
    }
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = extractErrorDetail(body) ?? detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(resp.status, detail);
  }

  return (await resp.json()) as T;
}

/** For binary responses (PDF-Downloads): plain fetch() ignores the
 * Authorization header a browser would need for a bare <a href>, so PDF
 * links go through this instead -- fetch the bytes with the token attached,
 * then hand the caller an object URL to open/download. */
export async function apiFetchBlob(path: string, _isRetry = false): Promise<Blob> {
  const token = authStore.getActiveAccessToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetchWithTimeout(`${BASE_URL}${path}`, { headers });

  if (resp.status === 401 && !_isRetry) {
    if (authStore.isImpersonating()) {
      authStore.setImpersonation(null);
      return apiFetchBlob(path, true);
    }
    if (await refreshPrimaryToken()) {
      return apiFetchBlob(path, true);
    }
  }

  if (!resp.ok) {
    throw new ApiError(resp.status, resp.statusText);
  }
  return await resp.blob();
}
