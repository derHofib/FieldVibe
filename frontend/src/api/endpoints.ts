import { apiFetch, apiFetchBlob, apiFetchForm } from "./client";
import { kundenApiFetch, kundenApiFetchBlob } from "./kundenClient";
import type {
  AccountTyp,
  AccountTypCreate,
  AccountTypUpdate,
  Adresse,
  Angebot,
  AngebotPosition,
  AngebotPositionstyp,
  Anlage,
  AnlagenFeldDefinition,
  AnlagenFeldTyp,
  AnlagenObjekttyp,
  AnlageProfil,
  Ansprechpartner,
  AuditLogEntry,
  Bestellung,
  BottomNavPraeferenz,
  CurrentKunde,
  CurrentUser,
  Dauerauftrag,
  DauerauftragMitVerlauf,
  DauerauftragModus,
  DsgvoDokument,
  DsgvoDokumentTyp,
  Eingangsrechnung,
  EingangsrechnungBelegUrl,
  EingangsrechnungPosition,
  EmailLog,
  FahrzeugZuweisungUebersicht,
  FeedResponse,
  Formular,
  FormularAuftragstypZuordnung,
  Formularfeld,
  FormularfeldDatenquelle,
  FormularfeldPosition,
  FormularfeldTyp,
  FormularVerfuegbar,
  GespeicherterFilter,
  GespeicherterFilterEntitaet,
  Highlight,
  ImpersonateResponse,
  Insights,
  InventurZyklus,
  Kunde,
  KundeLogoUrl,
  KundeProfil,
  KundenportalLinkInfo,
  KundenportalZugang,
  Leistungstyp,
  Lieferant,
  MailAccount,
  MailAccountVerbindungTest,
  MailFolder,
  MailMessageDetail,
  MailMessageListResponse,
  Mandant,
  MandantEinstellungen,
  MandantFirmendaten,
  MandantIntegration,
  MandantLogoUrl,
  Mangel,
  Material,
  MaterialBedarf,
  MaterialBedarfMitDetails,
  MaterialBedarfZweck,
  MaterialBewegung,
  MaterialVerwendung,
  NotificationEntry,
  OffenePostenBericht,
  PapierkorbEintrag,
  PapierkorbEntityTyp,
  Pruefmittel,
  Pruefzyklus,
  PruefzyklusEinheit,
  Rechnung,
  RechnungenFilter,
  RechnungListe,
  RechnungPosition,
  RechnungZahlungCreate,
  RechteAktion,
  RechteBereich,
  RechteMatrixEintrag,
  SearchResponse,
  Standort,
  StandortProfil,
  StoriesResponse,
  SystemHealth,
  SystemResources,
  Tag,
  TagAssignment,
  TagEntityType,
  TechnikerZuweisungUebersicht,
  Termin,
  TerminCreateResult,
  TokenPair,
  UstVaBericht,
  User,
  VersionInfo,
  Vorgang,
  VorgangAnfrage,
  VorgangEvent,
  VorgangEventType,
  VorgangFormular,
  Zeiterfassung,
  ZeiterfassungKategorie,
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

export const systemApi = {
  // /healthz liegt bewusst ausserhalb von /api und braucht kein Login (fuer
  // externes Infra-Monitoring per curl) -- dieselbe Antwort wird hier
  // wiederverwendet, um sie zusaetzlich im Super-Admin-Bereich anzuzeigen.
  healthz: () => apiFetch<SystemHealth>("/healthz"),
  // CPU/RAM/Speicher stecken bewusst hinter super_admin-Login (anders als
  // /healthz), da sie mehr ueber die Infrastruktur verraten.
  resources: () => apiFetch<SystemResources>("/api/admin/system/resources"),
};

export const versionApi = {
  get: () => apiFetch<VersionInfo>("/api/admin/version"),
};

export const mandantenApi = {
  list: () => apiFetch<Mandant[]>("/api/admin/mandanten"),
  get: (id: string) => apiFetch<Mandant>(`/api/admin/mandanten/${id}`),
  create: (body: { name: string; slug: string; branche?: string }) =>
    apiFetch<Mandant>("/api/admin/mandanten", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (
    id: string,
    body: Partial<Pick<Mandant, "name" | "branche" | "status" | "deaktivierte_module">>,
  ) =>
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
    account_typ_id?: string | null;
    name: string;
  }) =>
    apiFetch<User>("/api/users", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (
    id: string,
    body: Partial<Pick<User, "name" | "role" | "account_typ_id" | "aktiv">>,
  ) =>
    apiFetch<User>(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: string) => apiFetch<void>(`/api/users/${id}`, { method: "DELETE" }),
  updateOwnBottomNav: (praeferenz: BottomNavPraeferenz) =>
    apiFetch<BottomNavPraeferenz>("/api/users/me/bottom-nav", {
      method: "PATCH",
      body: JSON.stringify(praeferenz),
    }),
};

export const accountTypenApi = {
  list: () => apiFetch<AccountTyp[]>("/api/account-typen"),
  create: (body: AccountTypCreate) =>
    apiFetch<AccountTyp>("/api/account-typen", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: AccountTypUpdate) =>
    apiFetch<AccountTyp>(`/api/account-typen/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: string) => apiFetch<void>(`/api/account-typen/${id}`, { method: "DELETE" }),
  getRechte: (id: string) =>
    apiFetch<RechteMatrixEintrag[]>(`/api/account-typen/${id}/rechte`),
  setRecht: (id: string, bereich: RechteBereich, aktion: RechteAktion, erlaubt: boolean) =>
    apiFetch<RechteMatrixEintrag[]>(`/api/account-typen/${id}/rechte`, {
      method: "PUT",
      body: JSON.stringify({ bereich, aktion, erlaubt }),
    }),
};

export const auditLogApi = {
  list: (params: { mandant_id?: string; aktion?: string; von?: string; bis?: string; limit?: number } = {}) => {
    const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
    const qs = new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
    return apiFetch<AuditLogEntry[]>(`/api/admin/audit-log${qs ? `?${qs}` : ""}`);
  },
};

export const dsgvoApi = {
  list: () => apiFetch<DsgvoDokument[]>("/api/admin/dsgvo-dokumente"),
  upload: (typ: DsgvoDokumentTyp, file: File) => {
    const formData = new FormData();
    formData.append("file", file, file.name);
    return apiFetchForm<DsgvoDokument>(`/api/admin/dsgvo-dokumente/${typ}`, formData);
  },
  downloadUrl: (typ: DsgvoDokumentTyp) =>
    apiFetch<{ url: string }>(`/api/admin/dsgvo-dokumente/${typ}/download-url`),
  remove: (typ: DsgvoDokumentTyp) =>
    apiFetch<void>(`/api/admin/dsgvo-dokumente/${typ}`, { method: "DELETE" }),
};

export const papierkorbApi = {
  list: (entityTyp?: PapierkorbEntityTyp) =>
    apiFetch<PapierkorbEintrag[]>(
      `/api/papierkorb${entityTyp ? `?entity_typ=${entityTyp}` : ""}`,
    ),
  wiederherstellen: (entityTyp: PapierkorbEntityTyp, id: string) =>
    apiFetch<void>(`/api/papierkorb/${entityTyp}/${id}/wiederherstellen`, { method: "POST" }),
  endgueltigLoeschen: (entityTyp: PapierkorbEntityTyp, id: string) =>
    apiFetch<void>(`/api/papierkorb/${entityTyp}/${id}`, { method: "DELETE" }),
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
  create: (body: {
    name: string;
    typ?: string;
    kundennummer?: string;
    adresse?: Adresse;
    notiz?: string;
    ust_idnr?: string;
  }) => apiFetch<Kunde>("/api/kunden", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<{
      name: string;
      typ: string | null;
      adresse: Adresse | null;
      notiz: string | null;
      ust_idnr: string | null;
      ansprechpartner: Ansprechpartner[];
    }>,
  ) => apiFetch<Kunde>(`/api/kunden/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => apiFetch<void>(`/api/kunden/${id}`, { method: "DELETE" }),
  technikerListe: (id: string) => apiFetch<User[]>(`/api/kunden/${id}/techniker`),
  technikerSetzen: (id: string, userIds: string[]) =>
    apiFetch<User[]>(`/api/kunden/${id}/techniker`, {
      method: "PUT",
      body: JSON.stringify({ user_ids: userIds }),
    }),
  logoUpload: (id: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file, file.name);
    return apiFetchForm<Kunde>(`/api/kunden/${id}/logo`, formData);
  },
  logoRemove: (id: string) => apiFetch<Kunde>(`/api/kunden/${id}/logo`, { method: "DELETE" }),
  logoUrl: (id: string) => apiFetch<KundeLogoUrl>(`/api/kunden/${id}/logo-url`),
  emails: (id: string) => apiFetch<EmailLog[]>(`/api/kunden/${id}/emails`),
  sendEmail: (id: string, body: { empfaenger: string; betreff: string; inhalt: string }) =>
    apiFetch<EmailLog>(`/api/kunden/${id}/emails`, { method: "POST", body: JSON.stringify(body) }),
  // Auskunftsersuchen/Datenuebertragbarkeit (Art. 15/20 DSGVO) -- liefert
  // JSON, wird aber wie ein Datei-Download behandelt statt getypt zu werden,
  // da der Inhalt nur zum Speichern gedacht ist.
  datenexport: (id: string) => apiFetchBlob(`/api/kunden/${id}/datenexport`),
};

export const technikerZuweisungenApi = {
  uebersicht: () =>
    apiFetch<TechnikerZuweisungUebersicht[]>("/api/techniker-zuweisungen"),
};

export const anlagenApi = {
  list: (kundeId?: string, objekttyp?: AnlagenObjekttyp, aktiv?: boolean, standortId?: string) => {
    const params = new URLSearchParams();
    if (kundeId) params.set("kunde_id", kundeId);
    if (objekttyp) params.set("objekttyp", objekttyp);
    if (aktiv !== undefined) params.set("aktiv", String(aktiv));
    if (standortId) params.set("standort_id", standortId);
    const qs = params.toString();
    return apiFetch<Anlage[]>(`/api/anlagen${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<Anlage>(`/api/anlagen/${id}`),
  profil: (id: string) => apiFetch<AnlageProfil>(`/api/anlagen/${id}/profil`),
  byQrCode: (qrCode: string) => apiFetch<Anlage>(`/api/anlagen/by-qr/${encodeURIComponent(qrCode)}`),
  create: (body: {
    kunde_id?: string;
    standort_id?: string | null;
    objekttyp?: AnlagenObjekttyp;
    bezeichnung: string;
    anlagentyp?: string;
    hersteller?: string;
    modell?: string;
    seriennummer?: string;
    anschaffungsdatum?: string;
    notiz?: string;
    stammdaten?: Record<string, unknown>;
  }) => apiFetch<Anlage>("/api/anlagen", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<{
      standort_id: string | null;
      bezeichnung: string;
      adresse: Adresse;
      anlagentyp: string | null;
      aktiv: boolean;
      hersteller: string | null;
      modell: string | null;
      seriennummer: string | null;
      anschaffungsdatum: string | null;
      notiz: string | null;
      stammdaten: Record<string, unknown>;
    }>,
  ) => apiFetch<Anlage>(`/api/anlagen/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => apiFetch<void>(`/api/anlagen/${id}`, { method: "DELETE" }),
};

export const anlagenFeldDefinitionenApi = {
  list: (anlagentyp?: string) =>
    apiFetch<AnlagenFeldDefinition[]>(
      `/api/anlagen-feld-definitionen${anlagentyp ? `?anlagentyp=${encodeURIComponent(anlagentyp)}` : ""}`,
    ),
  create: (body: { anlagentyp: string; feld_name: string; feld_typ: AnlagenFeldTyp; reihenfolge?: number }) =>
    apiFetch<AnlagenFeldDefinition>("/api/anlagen-feld-definitionen", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: Partial<{ feld_name: string; feld_typ: AnlagenFeldTyp; reihenfolge: number }>) =>
    apiFetch<AnlagenFeldDefinition>(`/api/anlagen-feld-definitionen/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: string) => apiFetch<void>(`/api/anlagen-feld-definitionen/${id}`, { method: "DELETE" }),
};

export const standorteApi = {
  list: (kundeId?: string, aktiv?: boolean) => {
    const params = new URLSearchParams();
    if (kundeId) params.set("kunde_id", kundeId);
    if (aktiv !== undefined) params.set("aktiv", String(aktiv));
    const qs = params.toString();
    return apiFetch<Standort[]>(`/api/standorte${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<Standort>(`/api/standorte/${id}`),
  profil: (id: string) => apiFetch<StandortProfil>(`/api/standorte/${id}/profil`),
  create: (body: { kunde_id: string; bezeichnung: string; adresse?: Adresse }) =>
    apiFetch<Standort>("/api/standorte", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<{ bezeichnung: string; adresse: Adresse; aktiv: boolean }>) =>
    apiFetch<Standort>(`/api/standorte/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => apiFetch<void>(`/api/standorte/${id}`, { method: "DELETE" }),
};

export const gespeicherteFilterApi = {
  list: (entitaet: GespeicherterFilterEntitaet) =>
    apiFetch<GespeicherterFilter[]>(`/api/gespeicherte-filter?entitaet=${entitaet}`),
  create: (body: {
    entitaet: GespeicherterFilterEntitaet;
    name: string;
    filter_json: Record<string, string>;
    ist_standard?: boolean;
  }) =>
    apiFetch<GespeicherterFilter>("/api/gespeicherte-filter", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: Partial<{ name: string; filter_json: Record<string, string>; ist_standard: boolean }>) =>
    apiFetch<GespeicherterFilter>(`/api/gespeicherte-filter/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: string) => apiFetch<void>(`/api/gespeicherte-filter/${id}`, { method: "DELETE" }),
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
    weitere_anlage_ids?: string[];
    standort_id?: string | null;
    titel: string;
    beschreibung?: string;
    abrechnungsart: string;
    leistungstyp: string;
    prioritaet?: number;
    faelligkeit_am?: string | null;
    adresse?: Adresse | null;
    client_uuid?: string;
  }) => apiFetch<Vorgang>("/api/vorgaenge", { method: "POST", body: JSON.stringify(body) }),
  anlagen: (vorgangId: string) => apiFetch<Anlage[]>(`/api/vorgaenge/${vorgangId}/anlagen`),
  anlagenHinzufuegen: (vorgangId: string, anlageIds: string[]) =>
    apiFetch<Anlage[]>(`/api/vorgaenge/${vorgangId}/anlagen`, {
      method: "POST",
      body: JSON.stringify({ anlage_ids: anlageIds }),
    }),
  anlageEntfernen: (vorgangId: string, anlageId: string) =>
    apiFetch<void>(`/api/vorgaenge/${vorgangId}/anlagen/${anlageId}`, { method: "DELETE" }),
  update: (
    id: string,
    body: Partial<
      Pick<
        Vorgang,
        | "status"
        | "titel"
        | "beschreibung"
        | "prioritaet"
        | "kunde_id"
        | "anlage_id"
        | "standort_id"
        | "faelligkeit_am"
        | "adresse"
        | "zugewiesener_user_id"
      >
    > & {
      // Nur bei status="wartet_kunde" gueltig -- ueberschreibt die
      // Wiedervorlage-Frist (Tage ab jetzt), sonst greift der Mandanten-
      // bzw. globale Default.
      wiedervorlage_tage?: number;
    }
  ) => apiFetch<Vorgang>(`/api/vorgaenge/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  folgeAuftrag: (id: string, leistungstyp: Leistungstyp) =>
    apiFetch<Vorgang>(`/api/vorgaenge/${id}/folge-auftrag`, {
      method: "POST",
      body: JSON.stringify({ leistungstyp }),
    }),
  remove: (id: string) => apiFetch<void>(`/api/vorgaenge/${id}`, { method: "DELETE" }),
  uebernehmen: (id: string) =>
    apiFetch<Vorgang>(`/api/vorgaenge/${id}/uebernehmen`, { method: "POST" }),
  emails: (id: string) => apiFetch<EmailLog[]>(`/api/vorgaenge/${id}/emails`),
  sendEmail: (id: string, body: { empfaenger: string; betreff: string; inhalt: string }) =>
    apiFetch<EmailLog>(`/api/vorgaenge/${id}/emails`, { method: "POST", body: JSON.stringify(body) }),
};

export const vorgangAnfragenApi = {
  list: (status?: string) =>
    apiFetch<VorgangAnfrage[]>(`/api/vorgang-anfragen${status ? `?status=${status}` : ""}`),
  get: (id: string) => apiFetch<VorgangAnfrage>(`/api/vorgang-anfragen/${id}`),
  annehmen: (id: string, body: { abrechnungsart: string; prioritaet?: number }) =>
    apiFetch<VorgangAnfrage>(`/api/vorgang-anfragen/${id}/annehmen`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  ablehnen: (id: string, ablehnungsgrund?: string) =>
    apiFetch<VorgangAnfrage>(`/api/vorgang-anfragen/${id}/ablehnen`, {
      method: "POST",
      body: JSON.stringify({ ablehnungsgrund }),
    }),
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
    clientUuid?: string,
  ) => {
    const formData = new FormData();
    formData.append("file", file, filename);
    formData.append("kundensichtbar", String(kundensichtbar));
    if (body) formData.append("body", body);
    if (clientUuid) formData.append("client_uuid", clientUuid);
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

export const formulareApi = {
  list: (aktiv?: boolean) =>
    apiFetch<Formular[]>(`/api/formulare${aktiv !== undefined ? `?aktiv=${aktiv}` : ""}`),
  get: (id: string) => apiFetch<Formular>(`/api/formulare/${id}`),
  create: (body: { name: string; beschreibung?: string; snap_mm?: number | null }) =>
    apiFetch<Formular>("/api/formulare", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<{
      name: string;
      beschreibung: string;
      aktiv: boolean;
      snap_mm: number | null;
      anzahl_seiten: number;
    }>,
  ) => apiFetch<Formular>(`/api/formulare/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  createFeld: (
    formularId: string,
    body: {
      feld_typ: FormularfeldTyp;
      label: string;
      hilfetext?: string;
      pflichtfeld?: boolean;
      optionen?: Record<string, unknown>;
      seite?: number;
      x_mm?: number;
      y_mm?: number;
      breite_mm?: number;
      hoehe_mm?: number;
      datenquelle?: FormularfeldDatenquelle | null;
    },
  ) =>
    apiFetch<Formularfeld>(`/api/formulare/${formularId}/felder`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateFeld: (
    formularId: string,
    feldId: string,
    body: Partial<{
      feld_typ: FormularfeldTyp;
      label: string;
      hilfetext: string | null;
      pflichtfeld: boolean;
      optionen: Record<string, unknown>;
      datenquelle: FormularfeldDatenquelle | null;
    }>,
  ) =>
    apiFetch<Formularfeld>(`/api/formulare/${formularId}/felder/${feldId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  updatePositionen: (formularId: string, positionen: FormularfeldPosition[]) =>
    apiFetch<Formularfeld[]>(`/api/formulare/${formularId}/felder/positionen`, {
      method: "PUT",
      body: JSON.stringify(positionen),
    }),
  deleteFeld: (formularId: string, feldId: string) =>
    apiFetch<void>(`/api/formulare/${formularId}/felder/${feldId}`, { method: "DELETE" }),
  createZuordnung: (formularId: string, body: { leistungstyp: Leistungstyp; pflicht_vor_abschluss?: boolean }) =>
    apiFetch<FormularAuftragstypZuordnung>(`/api/formulare/${formularId}/zuordnungen`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateZuordnung: (formularId: string, zuordnungId: string, pflichtVorAbschluss: boolean) =>
    apiFetch<FormularAuftragstypZuordnung>(`/api/formulare/${formularId}/zuordnungen/${zuordnungId}`, {
      method: "PATCH",
      body: JSON.stringify({ pflicht_vor_abschluss: pflichtVorAbschluss }),
    }),
  deleteZuordnung: (formularId: string, zuordnungId: string) =>
    apiFetch<void>(`/api/formulare/${formularId}/zuordnungen/${zuordnungId}`, { method: "DELETE" }),
};

export const vorgangFormulareApi = {
  verfuegbar: (vorgangId: string) =>
    apiFetch<FormularVerfuegbar[]>(`/api/vorgang-formulare/verfuegbar?vorgang_id=${vorgangId}`),
  list: (vorgangId: string) =>
    apiFetch<VorgangFormular[]>(`/api/vorgang-formulare?vorgang_id=${vorgangId}`),
  start: (vorgangId: string, formularId: string) =>
    apiFetch<VorgangFormular>(`/api/vorgang-formulare?vorgang_id=${vorgangId}`, {
      method: "POST",
      body: JSON.stringify({ formular_id: formularId }),
    }),
  get: (id: string) => apiFetch<VorgangFormular>(`/api/vorgang-formulare/${id}`),
  updateAntworten: (id: string, antworten: Record<string, unknown>) =>
    apiFetch<VorgangFormular>(`/api/vorgang-formulare/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ antworten }),
    }),
  abschliessen: (id: string) =>
    apiFetch<VorgangFormular>(`/api/vorgang-formulare/${id}/abschliessen`, { method: "POST" }),
  remove: (id: string) => apiFetch<void>(`/api/vorgang-formulare/${id}`, { method: "DELETE" }),
  pdf: (id: string) => apiFetchBlob(`/api/vorgang-formulare/${id}/pdf`),
  uploadDatei: (id: string, feldId: string, file: Blob, filename: string) => {
    const formData = new FormData();
    formData.append("file", file, filename);
    return apiFetchForm<{ feld_id: string; key: string; content_type: string; size: number; url: string }>(
      `/api/vorgang-formulare/${id}/dateien?feld_id=${encodeURIComponent(feldId)}`,
      formData,
    );
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
  manuellErfassen: (body: {
    start_at: string;
    ende_at: string;
    kategorie: ZeiterfassungKategorie;
    vorgang_id?: string;
    taetigkeit?: string;
    abrechenbar?: boolean;
  }) =>
    apiFetch<Zeiterfassung>("/api/zeiterfassung/manuell", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  aktualisieren: (
    id: string,
    body: Partial<{
      start_at: string;
      ende_at: string;
      kategorie: ZeiterfassungKategorie;
      vorgang_id: string | null;
      taetigkeit: string;
      abrechenbar: boolean;
    }>
  ) => apiFetch<Zeiterfassung>(`/api/zeiterfassung/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  loeschen: (id: string) => apiFetch<void>(`/api/zeiterfassung/${id}`, { method: "DELETE" }),
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
  remove: (id: string) => apiFetch<void>(`/api/termine/${id}`, { method: "DELETE" }),
};

export const pruefzyklenApi = {
  list: (anlageId?: string) =>
    apiFetch<Pruefzyklus[]>(`/api/pruefzyklen${anlageId ? `?anlage_id=${anlageId}` : ""}`),
  create: (body: {
    anlage_id: string;
    bezeichnung: string;
    intervall_wert: number;
    intervall_einheit: PruefzyklusEinheit;
    letzte_pruefung_am?: string;
  }) => apiFetch<Pruefzyklus>("/api/pruefzyklen", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<
      Pick<Pruefzyklus, "bezeichnung" | "intervall_wert" | "intervall_einheit" | "letzte_pruefung_am" | "aktiv">
    >,
  ) =>
    apiFetch<Pruefzyklus>(`/api/pruefzyklen/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: string) => apiFetch<void>(`/api/pruefzyklen/${id}`, { method: "DELETE" }),
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
  remove: (id: string) => apiFetch<void>(`/api/inventurzyklen/${id}`, { method: "DELETE" }),
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
  remove: (id: string) => apiFetch<void>(`/api/pruefmittel/${id}`, { method: "DELETE" }),
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
  remove: (id: string) => apiFetch<void>(`/api/maengel/${id}`, { method: "DELETE" }),
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
  createFromMaterialBedarfe: (materialBedarfIds: string[], gueltigBis?: string) =>
    apiFetch<Angebot>("/api/angebote/from-material-bedarfe", {
      method: "POST",
      body: JSON.stringify({ material_bedarf_ids: materialBedarfIds, gueltig_bis: gueltigBis }),
    }),
  createFromVorgang: (vorgangId: string, gueltigBis?: string) =>
    apiFetch<Angebot>("/api/angebote/from-vorgang", {
      method: "POST",
      body: JSON.stringify({ vorgang_id: vorgangId, gueltig_bis: gueltigBis }),
    }),
  addPosition: (
    id: string,
    body: Pick<AngebotPosition, "beschreibung" | "menge" | "einheit" | "einzelpreis"> & {
      artikelnummer?: string;
      positionstyp?: AngebotPositionstyp;
    },
  ) => apiFetch<Angebot>(`/api/angebote/${id}/positionen`, { method: "POST", body: JSON.stringify(body) }),
  updateStatus: (id: string, status: string) =>
    apiFetch<Angebot>(`/api/angebote/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  remove: (id: string) => apiFetch<void>(`/api/angebote/${id}`, { method: "DELETE" }),
  pdf: (id: string) => apiFetchBlob(`/api/angebote/${id}/pdf`),
  emails: (id: string) => apiFetch<EmailLog[]>(`/api/angebote/${id}/emails`),
  sendEmail: (id: string, body: { empfaenger: string; betreff?: string; inhalt?: string }) =>
    apiFetch<EmailLog>(`/api/angebote/${id}/email`, { method: "POST", body: JSON.stringify(body) }),
};

// Baut einen Query-String aus dem RechnungenFilter -- status ist ein Array
// (wiederholbarer Query-Param, das Backend liest ihn per FastAPI list[str]),
// alle anderen Felder sind einfache Werte. undefined/leere Werte werden
// weggelassen statt als "undefined" mitgeschickt.
function rechnungenQueryString(filter: RechnungenFilter): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(filter)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const v of value) qs.append(key, String(v));
    } else {
      qs.append(key, String(value));
    }
  }
  return qs.toString();
}

export const rechnungenApi = {
  list: (filter: RechnungenFilter = {}) => {
    const qs = rechnungenQueryString(filter);
    return apiFetch<RechnungListe>(`/api/rechnungen${qs ? `?${qs}` : ""}`);
  },
  exportCsv: (filter: RechnungenFilter = {}) => {
    const qs = rechnungenQueryString(filter);
    return apiFetchBlob(`/api/rechnungen/export/csv${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<Rechnung>(`/api/rechnungen/${id}`),
  create: (body: {
    kunde_id: string;
    vorgang_id?: string | null;
    betrag_netto?: string;
    faellig_am?: string;
    leistungsdatum?: string;
    positionen?: Pick<RechnungPosition, "beschreibung" | "menge" | "einheit" | "einzelpreis">[];
  }) => apiFetch<Rechnung>("/api/rechnungen", { method: "POST", body: JSON.stringify(body) }),
  addPosition: (
    id: string,
    body: Pick<RechnungPosition, "beschreibung" | "menge" | "einheit" | "einzelpreis">,
  ) => apiFetch<Rechnung>(`/api/rechnungen/${id}/positionen`, { method: "POST", body: JSON.stringify(body) }),
  updateStatus: (id: string, status: string) =>
    apiFetch<Rechnung>(`/api/rechnungen/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  storno: (id: string) => apiFetch<Rechnung>(`/api/rechnungen/${id}/storno`, { method: "POST" }),
  remove: (id: string) => apiFetch<void>(`/api/rechnungen/${id}`, { method: "DELETE" }),
  pdf: (id: string) => apiFetchBlob(`/api/rechnungen/${id}/pdf`),
  xml: (id: string) => apiFetchBlob(`/api/rechnungen/${id}/xml`),
  emails: (id: string) => apiFetch<EmailLog[]>(`/api/rechnungen/${id}/emails`),
  sendEmail: (id: string, body: { empfaenger: string; betreff?: string; inhalt?: string }) =>
    apiFetch<EmailLog>(`/api/rechnungen/${id}/email`, { method: "POST", body: JSON.stringify(body) }),
  addZahlung: (id: string, body: RechnungZahlungCreate) =>
    apiFetch<Rechnung>(`/api/rechnungen/${id}/zahlungen`, { method: "POST", body: JSON.stringify(body) }),
  stornoZahlung: (id: string, zahlungId: string) =>
    apiFetch<Rechnung>(`/api/rechnungen/${id}/zahlungen/${zahlungId}/storno`, { method: "POST" }),
};

export const eingangsrechnungenApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<Eingangsrechnung[]>(`/api/eingangsrechnungen${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<Eingangsrechnung>(`/api/eingangsrechnungen/${id}`),
  create: (body: {
    lieferant_id?: string | null;
    lieferant_name?: string;
    vorgang_id?: string | null;
    rechnungsnummer_lieferant: string;
    rechnungsdatum: string;
    faellig_am?: string;
    betrag_netto?: string;
    skonto_prozent?: string;
    skonto_tage?: number;
    kategorie?: string;
    notiz?: string;
    positionen?: Pick<EingangsrechnungPosition, "beschreibung" | "menge" | "einheit" | "einzelpreis">[];
  }) => apiFetch<Eingangsrechnung>("/api/eingangsrechnungen", { method: "POST", body: JSON.stringify(body) }),
  addPosition: (
    id: string,
    body: Pick<EingangsrechnungPosition, "beschreibung" | "menge" | "einheit" | "einzelpreis">,
  ) =>
    apiFetch<Eingangsrechnung>(`/api/eingangsrechnungen/${id}/positionen`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  addZahlung: (id: string, body: { betrag: string; datum?: string }) =>
    apiFetch<Eingangsrechnung>(`/api/eingangsrechnungen/${id}/zahlungen`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (
    id: string,
    body: {
      status?: string;
      lieferant_id?: string | null;
      lieferant_name?: string;
      rechnungsnummer_lieferant?: string;
      rechnungsdatum?: string;
      betrag_netto?: string;
      faellig_am?: string;
      skonto_prozent?: string;
      skonto_tage?: number;
      kategorie?: string;
      notiz?: string;
    },
  ) => apiFetch<Eingangsrechnung>(`/api/eingangsrechnungen/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => apiFetch<void>(`/api/eingangsrechnungen/${id}`, { method: "DELETE" }),
  belegUpload: (id: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetchForm<Eingangsrechnung>(`/api/eingangsrechnungen/${id}/beleg`, formData);
  },
  belegUrl: (id: string) => apiFetch<EingangsrechnungBelegUrl>(`/api/eingangsrechnungen/${id}/beleg-url`),
  belegRemove: (id: string) =>
    apiFetch<Eingangsrechnung>(`/api/eingangsrechnungen/${id}/beleg`, { method: "DELETE" }),
};

export const tagsApi = {
  list: () => apiFetch<Tag[]>("/api/tags"),
  create: (label: string) =>
    apiFetch<Tag>("/api/tags", { method: "POST", body: JSON.stringify({ label }) }),
  assignments: (entityType: TagEntityType, entityId: string) =>
    apiFetch<TagAssignment[]>(
      `/api/tags/assignments?entity_type=${entityType}&entity_id=${entityId}`,
    ),
  assign: (tagId: string, entityType: TagEntityType, entityId: string) =>
    apiFetch<TagAssignment>(`/api/tags/${tagId}/assignments`, {
      method: "POST",
      body: JSON.stringify({ entity_type: entityType, entity_id: entityId }),
    }),
  unassign: (tagId: string, entityType: TagEntityType, entityId: string) =>
    apiFetch<void>(
      `/api/tags/${tagId}/assignments?entity_type=${entityType}&entity_id=${entityId}`,
      { method: "DELETE" },
    ),
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
  list: (lagerId?: string) =>
    apiFetch<Material[]>(`/api/material${lagerId ? `?lager_id=${lagerId}` : ""}`),
  get: (id: string) => apiFetch<Material>(`/api/material/${id}`),
  create: (body: {
    bezeichnung: string;
    einheit?: string;
    mindestbestand?: string;
    einzelpreis?: string;
    lieferant_id?: string;
    artikelnummer?: string;
    bestell_url?: string;
    lager_id?: string;
    menge?: string;
  }) => apiFetch<Material>("/api/material", { method: "POST", body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<
      Pick<
        Material,
        "bezeichnung" | "einheit" | "mindestbestand" | "einzelpreis" | "lieferant_id" | "artikelnummer" | "bestell_url"
      >
    >,
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
  remove: (id: string) => apiFetch<void>(`/api/material/${id}`, { method: "DELETE" }),
};

export const lieferantenApi = {
  list: () => apiFetch<Lieferant[]>("/api/lieferanten"),
  create: (body: { name: string; email?: string; telefon?: string; notiz?: string }) =>
    apiFetch<Lieferant>("/api/lieferanten", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<Pick<Lieferant, "name" | "email" | "telefon" | "notiz">>) =>
    apiFetch<Lieferant>(`/api/lieferanten/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => apiFetch<void>(`/api/lieferanten/${id}`, { method: "DELETE" }),
};

export const materialBedarfeApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<MaterialBedarfMitDetails[]>(`/api/material-bedarfe${qs ? `?${qs}` : ""}`);
  },
  create: (body: { material_id: string; vorgang_id: string; menge: string; notiz?: string; zweck?: MaterialBedarfZweck }) =>
    apiFetch<MaterialBedarf>("/api/material-bedarfe", { method: "POST", body: JSON.stringify(body) }),
  remove: (id: string) => apiFetch<void>(`/api/material-bedarfe/${id}`, { method: "DELETE" }),
};

export const bestellungenApi = {
  list: () => apiFetch<Bestellung[]>("/api/bestellungen"),
  get: (id: string) => apiFetch<Bestellung>(`/api/bestellungen/${id}`),
  createFromBedarfe: (materialBedarfIds: string[], lieferantId?: string, notiz?: string) =>
    apiFetch<Bestellung>("/api/bestellungen/from-bedarfe", {
      method: "POST",
      body: JSON.stringify({ material_bedarf_ids: materialBedarfIds, lieferant_id: lieferantId, notiz }),
    }),
  update: (id: string, body: { status?: string; lieferant_id?: string | null; notiz?: string }) =>
    apiFetch<Bestellung>(`/api/bestellungen/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => apiFetch<void>(`/api/bestellungen/${id}`, { method: "DELETE" }),
  csv: (id: string) => apiFetchBlob(`/api/bestellungen/${id}/csv`),
  pdf: (id: string) => apiFetchBlob(`/api/bestellungen/${id}/pdf`),
  emails: (id: string) => apiFetch<EmailLog[]>(`/api/bestellungen/${id}/emails`),
  sendEmail: (id: string, body: { empfaenger: string; betreff?: string; inhalt?: string }) =>
    apiFetch<EmailLog>(`/api/bestellungen/${id}/email`, { method: "POST", body: JSON.stringify(body) }),
};

export const insightsApi = {
  get: () => apiFetch<Insights>("/api/insights"),
};

export const exportApi = {
  vorgaengeCsv: () => apiFetchBlob("/api/vorgaenge/export/csv"),
  zeiterfassungCsv: () => apiFetchBlob("/api/zeiterfassung/export/csv"),
  materialCsv: () => apiFetchBlob("/api/material/export/csv"),
  eingangsrechnungenCsv: () => apiFetchBlob("/api/eingangsrechnungen/export/csv"),
};

export const auswertungApi = {
  ustVa: (von: string, bis: string) =>
    apiFetch<UstVaBericht>(`/api/auswertung/ust-va?von=${von}&bis=${bis}`),
  datevExportCsv: (von: string, bis: string) =>
    apiFetchBlob(`/api/auswertung/datev-export?von=${von}&bis=${bis}`),
  offenePosten: () => apiFetch<OffenePostenBericht>("/api/auswertung/offene-posten"),
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
  linkInfo: (portalSlug: string) =>
    kundenApiFetch<KundenportalLinkInfo>(
      `/api/kundenportal/auth/link/${encodeURIComponent(portalSlug)}`,
    ),
  linkLogoUrl: (portalSlug: string) =>
    kundenApiFetch<KundeLogoUrl>(
      `/api/kundenportal/auth/link/${encodeURIComponent(portalSlug)}/logo-url`,
    ),
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
  update: (body: { scheduler_stunde_utc?: number | null; wiedervorlage_standard_tage?: number | null }) =>
    apiFetch<MandantEinstellungen>("/api/mandant/einstellungen", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  firmendatenSpeichern: (firmendaten: MandantFirmendaten) =>
    apiFetch<MandantEinstellungen>("/api/mandant/einstellungen", {
      method: "PATCH",
      body: JSON.stringify({ firmendaten }),
    }),
  logoUpload: (file: File) => {
    const formData = new FormData();
    formData.append("file", file, file.name);
    return apiFetchForm<MandantEinstellungen>("/api/mandant/einstellungen/logo", formData);
  },
  logoRemove: () =>
    apiFetch<MandantEinstellungen>("/api/mandant/einstellungen/logo", { method: "DELETE" }),
  logoUrl: () => apiFetch<MandantLogoUrl>("/api/mandant/einstellungen/logo-url"),
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

export const mailApi = {
  testVerbindung: (body: MailAccountVerbindungTest) =>
    apiFetch<void>("/api/mail-accounts/test-verbindung", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  accounts: {
    list: () => apiFetch<MailAccount[]>("/api/mail-accounts"),
    create: (body: MailAccountVerbindungTest & { name: string; email_adresse: string; signatur?: string | null }) =>
      apiFetch<MailAccount>("/api/mail-accounts", { method: "POST", body: JSON.stringify(body) }),
    update: (
      id: string,
      body: Partial<
        MailAccountVerbindungTest & { name: string; email_adresse: string; signatur: string | null; aktiv: boolean }
      >,
    ) => apiFetch<MailAccount>(`/api/mail-accounts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    delete: (id: string) => apiFetch<void>(`/api/mail-accounts/${id}`, { method: "DELETE" }),
  },
  folders: (accountId: string) => apiFetch<MailFolder[]>(`/api/mail-accounts/${accountId}/folders`),
  messages: (folderId: string, params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<MailMessageListResponse>(`/api/mail-folders/${folderId}/messages${qs ? `?${qs}` : ""}`);
  },
  message: (id: string) => apiFetch<MailMessageDetail>(`/api/mail-messages/${id}`),
  setGelesen: (id: string, gelesen: boolean) =>
    apiFetch<MailMessageDetail>(`/api/mail-messages/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ gelesen }),
    }),
  attachmentUrl: (messageId: string, attachmentId: string) =>
    apiFetch<{ url: string }>(`/api/mail-messages/${messageId}/attachments/${attachmentId}/url`),
  senden: (accountId: string, body: { an: string[]; cc?: string[]; bcc?: string[]; betreff: string; text: string }) =>
    apiFetch<void>(`/api/mail-accounts/${accountId}/senden`, { method: "POST", body: JSON.stringify(body) }),
  antworten: (messageId: string, body: { an: string[]; cc?: string[]; text: string }) =>
    apiFetch<void>(`/api/mail-messages/${messageId}/antworten`, { method: "POST", body: JSON.stringify(body) }),
  weiterleiten: (messageId: string, body: { an: string[]; text?: string }) =>
    apiFetch<void>(`/api/mail-messages/${messageId}/weiterleiten`, { method: "POST", body: JSON.stringify(body) }),
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
  standorte: () => kundenApiFetch<Standort[]>("/api/kundenportal/standorte"),
  standortAnlegen: (body: { bezeichnung: string; adresse?: Adresse }) =>
    kundenApiFetch<Standort>("/api/kundenportal/standorte", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  anlagen: () => kundenApiFetch<Anlage[]>("/api/kundenportal/anlagen"),
  anlageAnlegen: (body: { standort_id?: string | null; bezeichnung: string; adresse?: Adresse; anlagentyp?: string }) =>
    kundenApiFetch<Anlage>("/api/kundenportal/anlagen", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  anfragen: () => kundenApiFetch<VorgangAnfrage[]>("/api/kundenportal/anfragen"),
  anfrage: (id: string) => kundenApiFetch<VorgangAnfrage>(`/api/kundenportal/anfragen/${id}`),
  anfrageAnlegen: (body: {
    titel: string;
    beschreibung?: string;
    leistungstyp: Leistungstyp;
    standort_id?: string | null;
    anlage_id?: string | null;
  }) =>
    kundenApiFetch<VorgangAnfrage>("/api/kundenportal/anfragen", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
