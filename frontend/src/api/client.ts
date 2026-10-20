import { authStore } from "./authStore";
import type { UserTokenPair } from "../types";

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

// Das Refresh-Token ist ein HttpOnly-Cookie am API-Host (Path=/api/auth) und
// fuer JavaScript unsichtbar. Der Header sagt dem Server, dass es dieses Cookie
// nutzt und das Token nicht zusaetzlich im Body erwartet.
const COOKIE_HEADER = { "X-Refresh-Cookie": "1" };

function istAuthPfad(path: string): boolean {
  return path.startsWith("/api/auth/");
}

/** Tauscht das Refresh-Cookie (bzw. ein noch gespeichertes Alt-Token) gegen
 * einen neuen Access-Token. Loescht die Sitzung nur bei klarer Ablehnung, nicht
 * bei Netz-/Serverproblemen. */
async function refreshAccessToken(altToken?: string): Promise<boolean> {
  const resp = await fetchWithTimeout(`${BASE_URL}/api/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...COOKIE_HEADER },
    body: JSON.stringify(altToken ? { refresh_token: altToken } : {}),
  });
  if (!resp.ok) {
    if (resp.status === 401 || resp.status === 403) authStore.clear();
    return false;
  }
  const data = (await resp.json()) as UserTokenPair;
  authStore.setPrimary({ accessToken: data.access_token });
  return true;
}

async function refreshPrimaryToken(): Promise<boolean> {
  const primary = authStore.getState().primary;
  if (!primary) return false;
  return refreshAccessToken(primary.refreshToken);
}

/** Beim App-Start ohne gespeicherten Token: Sitzung aus dem Cookie holen
 * (z. B. nach Reload oder wenn die andere Shell app./office. schon angemeldet
 * ist). Liefert false, wenn es keine Sitzung gibt oder der Server nicht erreichbar ist. */
export async function sitzungAusCookieWiederherstellen(): Promise<boolean> {
  try {
    return await refreshAccessToken();
  } catch {
    return false;
  }
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
  const authPfad = istAuthPfad(path);
  if (authPfad) headers.set("X-Refresh-Cookie", "1");

  const resp = await fetchWithTimeout(`${BASE_URL}${path}`, {
    ...options,
    headers,
    ...(authPfad ? { credentials: "include" as const } : {}),
  });

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
    // Fehler kommen auch bei Downloads als JSON-`detail` (z. B. 422 des
    // DATEV-Exports mit dem fehlenden Erlöskonto); ohne Body bleibt statusText.
    let detail = resp.statusText;
    try {
      detail = extractErrorDetail(await resp.json()) ?? detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(resp.status, detail);
  }
  return await resp.blob();
}
