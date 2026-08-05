import { ApiError } from "./client";
import { kundenAuthStore } from "./kundenAuthStore";
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

async function refreshToken(): Promise<boolean> {
  const current = kundenAuthStore.getState();
  if (!current) return false;

  const resp = await fetchWithTimeout(`${BASE_URL}/api/kundenportal/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: current.refreshToken }),
  });
  if (!resp.ok) {
    kundenAuthStore.clear();
    return false;
  }
  const data = (await resp.json()) as TokenPair;
  kundenAuthStore.setTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
  return true;
}

export async function kundenApiFetch<T>(
  path: string,
  options: RequestInit = {},
  _isRetry = false,
): Promise<T> {
  const token = kundenAuthStore.getAccessToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetchWithTimeout(`${BASE_URL}${path}`, { ...options, headers });

  if (resp.status === 401 && !_isRetry && (await refreshToken())) {
    return kundenApiFetch<T>(path, options, true);
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export async function kundenApiFetchBlob(path: string, _isRetry = false): Promise<Blob> {
  const token = kundenAuthStore.getAccessToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetchWithTimeout(`${BASE_URL}${path}`, { headers });

  if (resp.status === 401 && !_isRetry && (await refreshToken())) {
    return kundenApiFetchBlob(path, true);
  }

  if (!resp.ok) {
    throw new ApiError(resp.status, resp.statusText);
  }
  return await resp.blob();
}
