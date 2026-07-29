import { apiFetch, apiFetchBlob, apiFetchForm } from "./client";
import { kundenApiFetch, kundenApiFetchBlob } from "./kundenClient";
import type {
  Angebot,
  AngebotPosition,
  Anlage,
  AnlageProfil,
  AuditLogEntry,
  CurrentKunde,
  CurrentUser,
  FeedResponse,
  Highlight,
  ImpersonateResponse,
  Insights,
  Kunde,
  KundeProfil,
  KundenportalZugang,
  Mandant,
  MandantEinstellungen,
  MandantIntegration,
  Mangel,
  Material,
  MaterialVerwendung,
  NotificationEntry,
  Pruefmittel,
  Pruefzyklus,
  Rechnung,
  RechnungPosition,
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
    client_uuid?: string;
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

export const maengelApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<Mangel[]>(`/api/maengel${qs ? `?${qs}` : ""}`);
  },
  create: (body: { vorgang_id: string; anlage_id?: string | null; beschreibung: string; schweregrad?: string }) =>
    apiFetch<Mangel>("/api/maengel", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<Pick<Mangel, "beschreibung" | "schweregrad" | "status">>) =>
    apiFetch<Mangel>(`/api/maengel/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  protokollPdf: (vorgangId: string) => apiFetchBlob(`/api/maengel/protokoll/pdf?vorgang_id=${vorgangId}`),
};

export const angeboteApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<Angebot[]>(`/api/angebote${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<Angebot>(`/api/angebote/${id}`),
  create: (body: { kunde_id: string; vorgang_id?: string | null; gueltig_bis?: string }) =>
    apiFetch<Angebot>("/api/angebote", { method: "POST", body: JSON.stringify(body) }),
  createFromMaengel: (mangelIds: string[], gueltigBis?: string) =>
    apiFetch<Angebot>("/api/angebote/from-maengel", {
      method: "POST",
      body: JSON.stringify({ mangel_ids: mangelIds, gueltig_bis: gueltigBis }),
    }),
  addPosition: (
    id: string,
    body: Pick<AngebotPosition, "beschreibung" | "menge" | "einheit" | "einzelpreis">,
  ) => apiFetch<Angebot>(`/api/angebote/${id}/positionen`, { method: "POST", body: JSON.stringify(body) }),
  updateStatus: (id: string, status: string) =>
    apiFetch<Angebot>(`/api/angebote/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  pdf: (id: string) => apiFetchBlob(`/api/angebote/${id}/pdf`),
};

export const rechnungenApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<Rechnung[]>(`/api/rechnungen${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<Rechnung>(`/api/rechnungen/${id}`),
  create: (body: {
    kunde_id: string;
    vorgang_id?: string | null;
    betrag_netto?: string;
    faellig_am?: string;
    positionen?: Pick<RechnungPosition, "beschreibung" | "menge" | "einheit" | "einzelpreis">[];
  }) => apiFetch<Rechnung>("/api/rechnungen", { method: "POST", body: JSON.stringify(body) }),
  addPosition: (
    id: string,
    body: Pick<RechnungPosition, "beschreibung" | "menge" | "einheit" | "einzelpreis">,
  ) => apiFetch<Rechnung>(`/api/rechnungen/${id}/positionen`, { method: "POST", body: JSON.stringify(body) }),
  updateStatus: (id: string, status: string) =>
    apiFetch<Rechnung>(`/api/rechnungen/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  pdf: (id: string) => apiFetchBlob(`/api/rechnungen/${id}/pdf`),
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

export const highlightsApi = {
  list: () => apiFetch<Highlight[]>("/api/highlights"),
  create: (vorgangEventId: number, titel?: string) =>
    apiFetch<Highlight>("/api/highlights", {
      method: "POST",
      body: JSON.stringify({ vorgang_event_id: vorgangEventId, titel }),
    }),
  remove: (id: string) => apiFetch<void>(`/api/highlights/${id}`, { method: "DELETE" }),
};

export const materialApi = {
  list: () => apiFetch<Material[]>("/api/material"),
  create: (body: { bezeichnung: string; einheit?: string; bestand?: string; mindestbestand?: string; einzelpreis?: string }) =>
    apiFetch<Material>("/api/material", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<Pick<Material, "bezeichnung" | "einheit" | "bestand" | "mindestbestand" | "einzelpreis">>,
  ) => apiFetch<Material>(`/api/material/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  verwenden: (materialId: string, vorgangId: string, menge: string) =>
    apiFetch<MaterialVerwendung>(`/api/material/${materialId}/verwendung`, {
      method: "POST",
      body: JSON.stringify({ vorgang_id: vorgangId, menge }),
    }),
};

export const insightsApi = {
  get: () => apiFetch<Insights>("/api/insights"),
};

export const kundenportalZugaengeApi = {
  list: (kundeId: string) => apiFetch<KundenportalZugang[]>(`/api/kunden/${kundeId}/portal-zugaenge`),
  create: (kundeId: string, body: { email: string; password: string; name: string }) =>
    apiFetch<KundenportalZugang>(`/api/kunden/${kundeId}/portal-zugaenge`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (
    kundeId: string,
    zugangId: string,
    body: { name?: string; aktiv?: boolean; password?: string },
  ) =>
    apiFetch<KundenportalZugang>(`/api/kunden/${kundeId}/portal-zugaenge/${zugangId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};

export const kundenportalAuthApi = {
  login: (email: string, password: string) =>
    kundenApiFetch<TokenPair>("/api/kundenportal/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => kundenApiFetch<CurrentKunde>("/api/kundenportal/auth/me"),
  passwortVergessen: (email: string) =>
    kundenApiFetch<void>("/api/kundenportal/auth/passwort-vergessen", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  passwortZuruecksetzen: (token: string, newPassword: string) =>
    kundenApiFetch<void>("/api/kundenportal/auth/passwort-zuruecksetzen", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    }),
};

export const mandantEinstellungenApi = {
  get: () => apiFetch<MandantEinstellungen>("/api/mandant/einstellungen"),
  update: (schedulerStundeUtc: number | null) =>
    apiFetch<MandantEinstellungen>("/api/mandant/einstellungen", {
      method: "PATCH",
      body: JSON.stringify({ scheduler_stunde_utc: schedulerStundeUtc }),
    }),
};

export const integrationenApi = {
  list: () => apiFetch<MandantIntegration[]>("/api/integrationen"),
  create: (body: { typ: string; config?: Record<string, unknown>; secret?: string; aktiv?: boolean }) =>
    apiFetch<MandantIntegration>("/api/integrationen", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (
    id: string,
    body: { config?: Record<string, unknown>; secret?: string | null; aktiv?: boolean },
  ) =>
    apiFetch<MandantIntegration>(`/api/integrationen/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  delete: (id: string) => apiFetch<void>(`/api/integrationen/${id}`, { method: "DELETE" }),
};

export const kundenportalApi = {
  vorgaenge: () => kundenApiFetch<Vorgang[]>("/api/kundenportal/vorgaenge"),
  vorgang: (id: string) => kundenApiFetch<Vorgang>(`/api/kundenportal/vorgaenge/${id}`),
  vorgangEvents: (id: string) => kundenApiFetch<VorgangEvent[]>(`/api/kundenportal/vorgaenge/${id}/events`),
  angebote: () => kundenApiFetch<Angebot[]>("/api/kundenportal/angebote"),
  angebot: (id: string) => kundenApiFetch<Angebot>(`/api/kundenportal/angebote/${id}`),
  antwortAufAngebot: (id: string, status: "angenommen" | "abgelehnt") =>
    kundenApiFetch<Angebot>(`/api/kundenportal/angebote/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  angebotPdf: (id: string) => kundenApiFetchBlob(`/api/kundenportal/angebote/${id}/pdf`),
  rechnungen: () => kundenApiFetch<Rechnung[]>("/api/kundenportal/rechnungen"),
  rechnungPdf: (id: string) => kundenApiFetchBlob(`/api/kundenportal/rechnungen/${id}/pdf`),
};
