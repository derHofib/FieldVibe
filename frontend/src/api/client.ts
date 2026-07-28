import { authStore } from "./authStore";
import type { TokenPair } from "../types";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function refreshPrimaryToken(): Promise<boolean> {
  const primary = authStore.getState().primary;
  if (!primary) return false;

  const resp = await fetch(`${BASE_URL}/api/auth/refresh`, {
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

  const resp = await fetch(`${BASE_URL}${path}`, { ...options, headers });

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
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}
