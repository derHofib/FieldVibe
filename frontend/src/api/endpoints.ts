import { apiFetch } from "./client";
import type {
  AuditLogEntry,
  CurrentUser,
  ImpersonateResponse,
  Mandant,
  TokenPair,
  User,
} from "../types";

export const authApi = {
  login: (email: string, password: string) =>
    apiFetch<TokenPair>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => apiFetch<CurrentUser>("/api/auth/me"),
};

export const mandantenApi = {
  list: () => apiFetch<Mandant[]>("/api/admin/mandanten"),
  create: (body: { name: string; slug: string; branche?: string }) =>
    apiFetch<Mandant>("/api/admin/mandanten", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: Partial<Pick<Mandant, "name" | "branche" | "status">>) =>
    apiFetch<Mandant>(`/api/admin/mandanten/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  impersonate: (id: string) =>
    apiFetch<ImpersonateResponse>(`/api/admin/mandanten/${id}/impersonate`, {
      method: "POST",
    }),
};

export const usersApi = {
  list: () => apiFetch<User[]>("/api/users"),
  create: (body: {
    mandant_id: string | null;
    email: string;
    password: string;
    role: string;
    name: string;
  }) =>
    apiFetch<User>("/api/users", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: Partial<Pick<User, "name" | "role" | "aktiv">>) =>
    apiFetch<User>(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};

export const auditLogApi = {
  list: () => apiFetch<AuditLogEntry[]>("/api/admin/audit-log"),
};
