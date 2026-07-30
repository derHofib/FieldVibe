import { apiFetch, apiFetchBlob, apiFetchForm } from "./client";
import { kundenApiFetch, kundenApiFetchBlob } from "./kundenClient";
import type {
  Angebot,
  AngebotPosition,
  Anlage,
  AnlagenObjekttyp,
  AnlageProfil,
  AuditLogEntry,
  CurrentKunde,
  CurrentUser,
  Dauerauftrag,
  DauerauftragMitVerlauf,
  DauerauftragModus,
  FahrzeugZuweisungUebersicht,
  FeedResponse,
  Highlight,
  ImpersonateResponse,
  Insights,
  InventurZyklus,
  Kunde,
  KundeProfil,
  KundenportalZugang,
  Mandant,
  MandantEinstellungen,
  MandantIntegration,
  Mangel,
  Material,
  MaterialBewegung,
  MaterialVerwendung,
  NotificationEntry,
  Pruefmittel,
  Pruefzyklus,
  Rechnung,
  RechnungPosition,
  SearchResponse,
  StoriesResponse,
  Tag,
  TechnikerZuweisungUebersicht,
  Termin,
  TerminCreateResult,
  TokenPair,
  User,
  Vorgang,
  VorgangEvent,
  VorgangEventType,
  Zeiterfassung,
  ZeiterfassungStatistik,
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
  technikerListe: (id: string) => apiFetch<User[]>(`/api/kunden/${id}/techniker`),
  technikerSetzen: (id: string, userIds: string[]) =>
    apiFetch<User[]>(`/api/kunden/${id}/techniker`, {
      method: "PUT",
      body: JSON.stringify({ user_ids: userIds }),
    }),
};

export const technikerZuweisungenApi = {
  uebersicht: () =>
    apiFetch<TechnikerZuweisungUebersicht[]>("/api/techniker-zuweisungen"),
};

export const anlagenApi = {
  list: (kundeId?: string, objekttyp?: AnlagenObjekttyp) => {
    const params = new URLSearchParams();
    if (kundeId) params.set("kunde_id", kundeId);
    if (objekttyp) params.set("objekttyp", objekttyp);
    const qs = params.toString();
    return apiFetch<Anlage[]>(`/api/anlagen${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<Anlage>(`/api/anlagen/${id}`),
  profil: (id: string) => apiFetch<AnlageProfil>(`/api/anlagen/${id}/profil`),
  byQrCode: (qrCode: string) => apiFetch<Anlage>(`/api/anlagen/by-qr/${encodeURIComponent(qrCode)}`),
  create: (body: {
    kunde_id?: string;
    objekttyp?: AnlagenObjekttyp;
    bezeichnung: string;
    anlagentyp?: string;
  }) => apiFetch<Anlage>("/api/anlagen", { method: "POST", body: JSON.stringify(body) }),
};

export const dauerauftraegeApi = {
  list: (kundeId?: string) =>
    apiFetch<Dauerauftrag[]>(`/api/dauerauftraege${kundeId ? `?kunde_id=${kundeId}` : ""}`),
  get: (id: string) => apiFetch<DauerauftragMitVerlauf>(`/api/dauerauftraege/${id}`),
  create: (body: {
    kunde_id: string;
    anlage_ids?: string[];
    titel: string;
    beschreibung?: string;
    abrechnungsart: string;
    leistungstyp: string;
    intervall_tage: number;
    naechste_faelligkeit_am: string;
    modus?: DauerauftragModus;
    toleranz_frueh_tage?: number;
    toleranz_spaet_tage?: number;
  }) => apiFetch<Dauerauftrag>("/api/dauerauftraege", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<{
      titel: string;
      beschreibung: string;
      abrechnungsart: string;
      leistungstyp: string;
      intervall_tage: number;
      modus: DauerauftragModus;
      toleranz_frueh_tage: number | null;
      toleranz_spaet_tage: number | null;
      aktiv: boolean;
    }>
  ) => apiFetch<Dauerauftrag>(`/api/dauerauftraege/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  setAnlagen: (id: string, body: { anlage_ids: string[]; naechste_faelligkeit_am: string }) =>
    apiFetch<Dauerauftrag>(`/api/dauerauftraege/${id}/anlagen`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  delete: (id: string) => apiFetch<void>(`/api/dauerauftraege/${id}`, { method: "DELETE" }),
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
  update: (
    id: string,
    body: Partial<
      Pick<Vorgang, "status" | "titel" | "beschreibung" | "prioritaet" | "kunde_id" | "anlage_id">
    >
  ) => apiFetch<Vorgang>(`/api/vorgaenge/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
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
  uploadUnterschrift: (
    vorgangId: string,
    file: Blob,
    unterzeichnerName: string,
    kundensichtbar: boolean = true,
  ) => {
    const formData = new FormData();
    formData.append("file", file, "unterschrift.png");
    formData.append("unterzeichner_name", unterzeichnerName);
    formData.append("kundensichtbar", String(kundensichtbar));
    return apiFetchForm<VorgangEvent>(`/api/vorgaenge/${vorgangId}/events/unterschrift`, formData);
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
  listFuerZeitraum: (params: { techniker_id?: string; von?: string; bis?: string }) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined) as [string, string][]
    ).toString();
    return apiFetch<Zeiterfassung[]>(`/api/zeiterfassung${qs ? `?${qs}` : ""}`);
  },
  statistik: (technikerId?: string) =>
    apiFetch<ZeiterfassungStatistik>(
      `/api/zeiterfassung/statistik${technikerId ? `?techniker_id=${technikerId}` : ""}`
    ),
  wochenzettelPdf: (wocheStart: string, technikerId?: string) =>
    apiFetchBlob(
      `/api/zeiterfassung/wochenzettel-pdf?woche_start=${wocheStart}${
        technikerId ? `&techniker_id=${technikerId}` : ""
      }`
    ),
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

export const inventurzyklenApi = {
  list: (lagerId?: string) =>
    apiFetch<InventurZyklus[]>(`/api/inventurzyklen${lagerId ? `?lager_id=${lagerId}` : ""}`),
  create: (body: { lager_id: string; intervall_tage: number; naechste_inventur_am?: string }) =>
    apiFetch<InventurZyklus>("/api/inventurzyklen", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<
      Pick<InventurZyklus, "intervall_tage" | "letzte_inventur_am" | "naechste_inventur_am" | "aktiv">
    >,
  ) =>
    apiFetch<InventurZyklus>(`/api/inventurzyklen/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};

export const fahrzeugZuweisungenApi = {
  uebersicht: () =>
    apiFetch<FahrzeugZuweisungUebersicht[]>("/api/fahrzeug-zuweisungen"),
  mir: () => apiFetch<Anlage | null>("/api/fahrzeug-zuweisungen/mir"),
  setzen: (userId: string, anlageId: string | null) =>
    apiFetch<Anlage | null>(`/api/fahrzeug-zuweisungen/${userId}`, {
      method: "PUT",
      body: JSON.stringify({ anlage_id: anlageId }),
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
  create: (body: {
    bezeichnung: string;
    einheit?: string;
    mindestbestand?: string;
    einzelpreis?: string;
    lager_id?: string;
    menge?: string;
  }) => apiFetch<Material>("/api/material", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<Pick<Material, "bezeichnung" | "einheit" | "mindestbestand" | "einzelpreis">>,
  ) => apiFetch<Material>(`/api/material/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  bestandSetzen: (materialId: string, lagerId: string, menge: string) =>
    apiFetch<Material>(`/api/material/${materialId}/bestand/${lagerId}`, {
      method: "PUT",
      body: JSON.stringify({ menge }),
    }),
  umlagern: (materialId: string, vonLagerId: string, nachLagerId: string, menge: string) =>
    apiFetch<Material>(`/api/material/${materialId}/umlagern`, {
      method: "POST",
      body: JSON.stringify({ von_lager_id: vonLagerId, nach_lager_id: nachLagerId, menge }),
    }),
  bewegungen: (materialId: string) =>
    apiFetch<MaterialBewegung[]>(`/api/material/${materialId}/bewegungen`),
  verwenden: (materialId: string, vorgangId: string, lagerId: string, menge: string) =>
    apiFetch<MaterialVerwendung>(`/api/material/${materialId}/verwendung`, {
      method: "POST",
      body: JSON.stringify({ vorgang_id: vorgangId, lager_id: lagerId, menge }),
    }),
};

export const insightsApi = {
  get: () => apiFetch<Insights>("/api/insights"),
};

export const exportApi = {
  vorgaengeCsv: () => apiFetchBlob("/api/vorgaenge/export/csv"),
  zeiterfassungCsv: () => apiFetchBlob("/api/zeiterfassung/export/csv"),
  materialCsv: () => apiFetchBlob("/api/material/export/csv"),
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
