import { apiFetch, apiFetchForm } from "./client";
import type {
  Anlage,
  AnlageProfil,
  AuditLogEntry,
  CurrentUser,
  FeedResponse,
  ImpersonateResponse,
  Kunde,
  KundeProfil,
  Mandant,
  NotificationEntry,
  Pruefmittel,
  Pruefzyklus,
  SearchResponse,
  StoriesResponse,
  Tag,
  Termin,
  TerminCreateResult,
  TokenPair,
  User,
  Vorgang,
  VorgangEvent,
  VorgangEventType,
  Zeiterfassung,
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

export const feedApi = {
  get: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<FeedResponse>(`/api/feed${qs ? `?${qs}` : ""}`);
  },
};

export const storiesApi = {
  get: () => apiFetch<StoriesResponse>("/api/stories"),
};

export const searchApi = {
  search: (q: string) => apiFetch<SearchResponse>(`/api/search?q=${encodeURIComponent(q)}`),
};

export const notificationsApi = {
  list: (nurUngelesen = false) =>
    apiFetch<NotificationEntry[]>(`/api/notifications?nur_ungelesen=${nurUngelesen}`),
  markRead: (id: number) =>
    apiFetch<NotificationEntry>(`/api/notifications/${id}/gelesen`, { method: "POST" }),
  markAllRead: () => apiFetch<void>("/api/notifications/gelesen", { method: "POST" }),
};

export const kundenApi = {
  list: (q?: string) => apiFetch<Kunde[]>(`/api/kunden${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  get: (id: string) => apiFetch<Kunde>(`/api/kunden/${id}`),
  profil: (id: string) => apiFetch<KundeProfil>(`/api/kunden/${id}/profil`),
  create: (body: { name: string; typ?: string; kundennummer?: string }) =>
    apiFetch<Kunde>("/api/kunden", { method: "POST", body: JSON.stringify(body) }),
};

export const anlagenApi = {
  list: (kundeId?: string) =>
    apiFetch<Anlage[]>(`/api/anlagen${kundeId ? `?kunde_id=${kundeId}` : ""}`),
  profil: (id: string) => apiFetch<AnlageProfil>(`/api/anlagen/${id}/profil`),
  byQrCode: (qrCode: string) => apiFetch<Anlage>(`/api/anlagen/by-qr/${encodeURIComponent(qrCode)}`),
};

export const vorgaengeApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<Vorgang[]>(`/api/vorgaenge${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<Vorgang>(`/api/vorgaenge/${id}`),
  create: (body: {
    kunde_id: string;
    anlage_id?: string | null;
    titel: string;
    beschreibung?: string;
    abrechnungsart: string;
    leistungstyp: string;
    prioritaet?: number;
  }) => apiFetch<Vorgang>("/api/vorgaenge", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<Pick<Vorgang, "status" | "titel" | "beschreibung" | "prioritaet">>) =>
    apiFetch<Vorgang>(`/api/vorgaenge/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
};

export const vorgangEventsApi = {
  list: (vorgangId: string) => apiFetch<VorgangEvent[]>(`/api/vorgaenge/${vorgangId}/events`),
  create: (
    vorgangId: string,
    body: {
      event_type: VorgangEventType;
      body?: string;
      kundensichtbar?: boolean;
      client_uuid?: string;
    },
  ) =>
    apiFetch<VorgangEvent>(`/api/vorgaenge/${vorgangId}/events`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  uploadFoto: (
    vorgangId: string,
    file: Blob,
    filename: string,
    kundensichtbar: boolean,
    body?: string,
  ) => {
    const formData = new FormData();
    formData.append("file", file, filename);
    formData.append("kundensichtbar", String(kundensichtbar));
    if (body) formData.append("body", body);
    return apiFetchForm<VorgangEvent>(`/api/vorgaenge/${vorgangId}/events/foto`, formData);
  },
};

export const zeiterfassungApi = {
  laufend: () => apiFetch<Zeiterfassung | null>("/api/zeiterfassung/laufend"),
  start: (vorgangId: string, taetigkeit?: string) =>
    apiFetch<Zeiterfassung>("/api/zeiterfassung/start", {
      method: "POST",
      body: JSON.stringify({ vorgang_id: vorgangId, taetigkeit }),
    }),
  stop: (id: string) =>
    apiFetch<Zeiterfassung>(`/api/zeiterfassung/${id}/stop`, { method: "POST" }),
  list: (vorgangId: string) =>
    apiFetch<Zeiterfassung[]>(`/api/zeiterfassung?vorgang_id=${vorgangId}`),
};

export const termineApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<Termin[]>(`/api/termine${qs ? `?${qs}` : ""}`);
  },
  create: (body: {
    vorgang_id: string;
    techniker_id: string;
    titel: string;
    start_at: string;
    ende_at: string;
    notiz?: string;
  }) => apiFetch<TerminCreateResult>("/api/termine", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<Pick<Termin, "titel" | "techniker_id" | "start_at" | "ende_at" | "status" | "notiz">>,
  ) =>
    apiFetch<TerminCreateResult>(`/api/termine/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};

export const pruefzyklenApi = {
  list: (anlageId?: string) =>
    apiFetch<Pruefzyklus[]>(`/api/pruefzyklen${anlageId ? `?anlage_id=${anlageId}` : ""}`),
  create: (body: {
    anlage_id: string;
    bezeichnung: string;
    intervall_monate: number;
    letzte_pruefung_am?: string;
  }) => apiFetch<Pruefzyklus>("/api/pruefzyklen", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<
      Pick<Pruefzyklus, "bezeichnung" | "intervall_monate" | "letzte_pruefung_am" | "aktiv">
    >,
  ) =>
    apiFetch<Pruefzyklus>(`/api/pruefzyklen/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};

export const pruefmittelApi = {
  list: (zugewiesenAn?: string) =>
    apiFetch<Pruefmittel[]>(`/api/pruefmittel${zugewiesenAn ? `?zugewiesen_an=${zugewiesenAn}` : ""}`),
  create: (body: {
    bezeichnung: string;
    seriennummer?: string;
    zugewiesen_an?: string | null;
    kalibrierintervall_monate: number;
    letzte_kalibrierung_am?: string;
  }) => apiFetch<Pruefmittel>("/api/pruefmittel", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<
      Pick<
        Pruefmittel,
        "bezeichnung" | "seriennummer" | "zugewiesen_an" | "kalibrierintervall_monate" | "letzte_kalibrierung_am" | "status"
      >
    >,
  ) =>
    apiFetch<Pruefmittel>(`/api/pruefmittel/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};

export const tagsApi = {
  list: () => apiFetch<Tag[]>("/api/tags"),
  create: (label: string) =>
    apiFetch<Tag>("/api/tags", { method: "POST", body: JSON.stringify({ label }) }),
  assign: (tagId: string, entityType: "kunde" | "anlage" | "vorgang", entityId: string) =>
    apiFetch(`/api/tags/${tagId}/assignments`, {
      method: "POST",
      body: JSON.stringify({ entity_type: entityType, entity_id: entityId }),
    }),
};
