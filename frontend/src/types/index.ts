export type MandantStatus = "aktiv" | "pausiert" | "gekuendigt";

// Antwort von GET /healthz (unauthentifiziert, fuer Infra-Monitoring UND
// die System-Status-Anzeige im Super-Admin-Bereich). scheduler_letzter_lauf
// ist null, solange der worker-Container noch keinen erfolgreichen
// stuendlichen Tick hatte (frisches Deployment).
export interface SystemHealth {
  status: string;
  scheduler_letzter_lauf: string | null;
}

// Antwort von GET /api/admin/system/resources -- super_admin-only, siehe
// app/services/system_resources_service.py. "verlauf" ist ein In-Memory-
// Ringpuffer (verliert Werte bei Backend-Neustart), fuer die Sparkline im
// Super-Admin-Dashboard.
export interface SystemResourceSample {
  timestamp: string;
  cpu_percent: number;
  ram_percent: number;
  ram_used_mb: number;
  ram_total_mb: number;
  disk_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
}

export interface SystemResources {
  aktuell: SystemResourceSample;
  verlauf: SystemResourceSample[];
}

// Antwort von GET /api/admin/version -- rein informativ (aktuell
// deployter Commit vs. neuester Commit auf GitHub). Zeigt bewusst keinen
// Update-Button: das Backend fuehrt kein Update selbst aus, siehe
// app/services/version_service.py.
export interface VersionInfo {
  deployed_commit: string;
  branch: string;
  latest_commit_sha: string | null;
  latest_commit_message: string | null;
  latest_commit_date: string | null;
  latest_commit_url: string | null;
  update_available: boolean | null;
  fehler: string | null;
}

// Muss mit DSGVO_DOKUMENT_TYPEN in backend/app/models/dsgvo_dokument.py
// uebereinstimmen.
export type DsgvoDokumentTyp =
  | "avv_vorlage"
  | "datenschutzerklaerung"
  | "impressum"
  | "loeschkonzept"
  | "tom_dokument"
  | "meldeprozess"
  | "verzeichnis_verarbeitungstaetigkeiten";

export interface DsgvoDokument {
  id: string;
  typ: DsgvoDokumentTyp;
  dateiname: string;
  content_type: string;
  groesse_bytes: number;
  hochgeladen_von: string;
  created_at: string;
  updated_at: string;
}

// "custom" ersetzt die vormals fest verdrahteten disponent/techniker/
// controller/mitarbeiter -- ein mandant_admin definiert beliebig viele
// eigene Account-Typen (siehe AccountTyp weiter unten) mit je eigener
// Rechte-Matrix statt einer festen Rollen-Liste.
export type Role =
  | "super_admin"
  | "mandant_admin"
  | "custom"
  | "loesch_ansicht"
  | "loesch_operativ";

// Muss mit MANDANT_MODULE in backend/app/models/mandant.py uebereinstimmen.
// "vorgaenge" (Auftrag + Chat/Foto/Status/Unterschrift + Zeit start/stopp,
// Kunde per Dropdown waehlen oder inline anlegen) ist bewusst NICHT Teil
// dieser Liste -- das ist der nicht abschaltbare Boden.
export type MandantModul =
  | "kundenverwaltung"
  | "dispo"
  | "material"
  | "pruefzyklen"
  | "abrechnung"
  | "kundenportal"
  | "dauerauftrag"
  | "statistik"
  | "fahrzeuge"
  | "highlights"
  | "karten"
  | "nachunternehmer"
  | "postfach";

export interface Mandant {
  id: string;
  name: string;
  slug: string;
  branche: string | null;
  status: MandantStatus;
  branding: Record<string, unknown>;
  deaktivierte_module: MandantModul[];
  created_at: string;
  updated_at: string;
}

export interface User {
  id: string;
  mandant_id: string | null;
  email: string;
  role: Role;
  account_typ_id: string | null;
  account_typ_name: string | null;
  nur_zugewiesene_kunden: boolean;
  name: string;
  avatar_url: string | null;
  aktiv: boolean;
  created_at: string;
  updated_at: string;
}

// Nur "mandant_admin"/"custom" -- fuer super_admin und die Papierkorb-Rollen
// gibt es keinen Einladungsweg (siehe app/schemas/einladung.py), die bleiben
// bei direkter Anlage mit Passwort.
export type EinladungRolle = "mandant_admin" | "custom";
export type EinladungStatus = "offen" | "angenommen" | "widerrufen";

export interface Einladung {
  id: string;
  email: string;
  art: "mitarbeiter" | "kunde" | "partner";
  rolle: EinladungRolle | null;
  account_typ_id: string | null;
  kunde_id: string | null;
  partner_id: string | null;
  status: EinladungStatus;
  abgelaufen: boolean;
  created_at: string;
  angenommen_am: string | null;
  // Immer gesetzt bei status "offen" (siehe schemas/einladung.py) --
  // erlaubt "Link kopieren" unabhaengig davon, ob die Einladungsmail
  // tatsaechlich verschickt wurde.
  registrierungslink: string | null;
}

// Muss mit ENTITY_REGISTRY in backend/app/services/papierkorb_service.py
// uebereinstimmen.
export type PapierkorbEntityTyp =
  | "kunde"
  | "anlage"
  | "vertrag"
  | "vorgang"
  | "standort"
  | "termin"
  | "pruefzyklus"
  | "pruefmittel"
  | "lieferant"
  | "material"
  | "material_bedarf"
  | "bestellung"
  | "dauerauftrag"
  | "dauerauftrag_ziel"
  | "mangel"
  | "angebot"
  | "rechnung"
  | "inventurzyklus"
  | "fahrzeug_zuweisung"
  | "tag"
  | "vorgang_anfrage";

export interface PapierkorbEintrag {
  entity_typ: PapierkorbEntityTyp;
  id: string;
  titel: string | null;
  geloescht_am: string;
  geloescht_von: string | null;
  geloescht_von_name: string | null;
}

export interface AuditLogEntry {
  id: number;
  mandant_id: string | null;
  actor_user_id: string | null;
  aktion: string;
  entity_type: string | null;
  entity_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface BottomNavPraeferenz {
  links: string[] | null;
  rotunde: string[] | null;
}

export interface OfficeNavPraeferenz {
  items: string[] | null;
}

// Frei konfigurierbare Menue-Kategorien fuer die Office-Seitenleiste (siehe
// config/navSeiten.ts: NAV_KATEGORIE_REIHENFOLGE ist der Fallback, wenn
// kategorien hier leer ist -- der Mandant hat dann noch nie etwas
// angepasst).
export interface NavKategorieEintrag {
  name: string;
  reihenfolge: number;
}

export interface NavKategorienRead {
  kategorien: NavKategorieEintrag[];
  // nav_key -> Kategorie-Name
  zuordnungen: Record<string, string>;
}

export interface CurrentUser {
  id: string;
  mandant_id: string | null;
  mandant_name: string | null;
  role: Role;
  account_typ_id: string | null;
  account_typ_name: string | null;
  nur_zugewiesene_kunden: boolean;
  // Steuert den "Ticket übernehmen"-Button auf der Vorgang-Detailseite
  // (siehe app/services/rechte_service.py:darf_vorgang_selbst_uebernehmen).
  darf_vorgaenge_selbst_uebernehmen: boolean;
  name: string;
  email: string;
  impersonated_by: string | null;
  deaktivierte_module: MandantModul[];
  // Individualisierte Bottom-Nav (siehe frontend/src/config/navSeiten.ts) --
  // links: feste Zone (genau 2 Seiten), rotunde: wischbare Zone (beliebig
  // viele) -- null = jeweils Standardauswahl verwenden.
  bottom_nav_items: BottomNavPraeferenz | null;
  // Individualisierte Office-Seitenleiste (siehe office/OfficeLayout.tsx) --
  // null = alle sichtbaren Seiten zeigen (Standardverhalten).
  office_nav_items: OfficeNavPraeferenz | null;
  // Bereich -> Liste erlaubter Aktionen fuer diese Session (siehe
  // app/api/routes/auth.py:me) -- role != "custom" bekommt immer alle
  // Bereiche/Aktionen.
  rechte: Partial<Record<RechteBereich, RechteAktion[]>>;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface ImpersonateResponse {
  access_token: string;
  token_type: string;
  mandant_id: string;
  expires_in_minutes: number;
}

// --- Fachlicher Kern (Phase 2) ------------------------------------------

export type KundeTyp = "privat" | "gewerbe" | "oeffentlich" | "hausverwaltung";

// 1 = Erstkontakt, 2 = Eskalation, 3 = Geschaeftsleitung/Notfall.
export type Eskalationsstufe = 1 | 2 | 3;

export interface Ansprechpartner {
  id: string;
  name: string;
  position: string | null;
  telefon: string | null;
  email: string | null;
  operativ: boolean;
  eskalationsstufe: Eskalationsstufe | null;
  notiz: string | null;
}

export interface Adresse {
  strasse?: string;
  plz?: string;
  ort?: string;
}

export interface Kunde {
  id: string;
  kundennummer: string;
  name: string;
  typ: KundeTyp | null;
  ansprechpartner: Ansprechpartner[];
  adresse: Adresse | null;
  notiz: string | null;
  ust_idnr: string | null;
  portal_slug: string;
  logo_object_key: string | null;
  created_at: string;
  updated_at: string;
}

export type AnlagenObjekttyp = "kundenanlage" | "fahrzeug" | "lager" | "baustelle";

export interface Anlage {
  id: string;
  kunde_id: string | null;
  standort_id: string | null;
  objekttyp: AnlagenObjekttyp;
  bezeichnung: string;
  adresse: Adresse;
  anlagentyp: string | null;
  qr_code: string | null;
  hersteller: string | null;
  modell: string | null;
  seriennummer: string | null;
  anschaffungsdatum: string | null;
  notiz: string | null;
  stammdaten: Record<string, unknown>;
  geo_lat: number | null;
  geo_lng: number | null;
  aktiv: boolean;
  erstellt_von_kundenportal_zugang_id: string | null;
  created_at: string;
  updated_at: string;
}

export type AnlagenFeldTyp = "text" | "zahl" | "datum";

export interface AnlagenFeldDefinition {
  id: string;
  anlagentyp: string;
  feld_name: string;
  feld_typ: AnlagenFeldTyp;
  reihenfolge: number;
  created_at: string;
  updated_at: string;
}

export interface Standort {
  id: string;
  kunde_id: string;
  bezeichnung: string;
  adresse: Adresse;
  aktiv: boolean;
  geo_lat: number | null;
  geo_lng: number | null;
  erstellt_von_kundenportal_zugang_id: string | null;
  created_at: string;
  updated_at: string;
}

export type VorgangStatus =
  | "neu"
  | "geplant"
  | "in_arbeit"
  | "wartet_kunde"
  | "abgeschlossen"
  | "abgerechnet"
  | "storniert";

export type VorgangAbrechnungsart =
  | "pauschale"
  | "aufwand"
  | "festpreis"
  | "wartungsvertrag"
  | "gewaehrleistung";

export type Leistungstyp = "installation" | "pruefung" | "wartung" | "stoerung" | "beratung" | "planung";

export interface Vorgang {
  id: string;
  vorgangsnummer: string;
  kunde_id: string;
  anlage_id: string | null;
  standort_id: string | null;
  vertrag_id: string | null;
  parent_vorgang_id: string | null;
  dauerauftrag_id: string | null;
  titel: string;
  beschreibung: string | null;
  abrechnungsart: VorgangAbrechnungsart;
  leistungstyp: Leistungstyp;
  status: VorgangStatus;
  prioritaet: number;
  faelligkeit_am: string | null;
  adresse: Adresse | null;
  zugewiesener_user_id: string | null;
  // Vom Backend server-seitig aufgeloest (siehe VorgangRead.zugewiesener_name).
  zugewiesener_name: string | null;
  last_activity_at: string;
  abgeschlossen_am: string | null;
  erstellt_von_kundenportal_zugang_id: string | null;
  erstellt_von: string | null;
  wiedervorlage_am: string | null;
  partner_id: string | null;
  partner_freigabe_status: PartnerFreigabeStatus | null;
  partner_ablehnung_grund: string | null;
  partner_honorar_netto: string | null;
  created_at: string;
  updated_at: string;
}

// --- Auftragsanfragen (Kundenportal) ----------------------------------------

export type VorgangAnfrageStatus = "offen" | "angenommen" | "abgelehnt";

export interface VorgangAnfrage {
  id: string;
  kunde_id: string;
  kundenportal_zugang_id: string;
  standort_id: string | null;
  anlage_id: string | null;
  titel: string;
  beschreibung: string | null;
  leistungstyp: Leistungstyp;
  status: VorgangAnfrageStatus;
  ablehnungsgrund: string | null;
  vorgang_id: string | null;
  bearbeitet_von: string | null;
  bearbeitet_am: string | null;
  created_at: string;
  updated_at: string;
}

export type VorgangEventType =
  | "kommentar"
  | "status_change"
  | "foto"
  | "dokument"
  | "mangel"
  | "angebot"
  | "material"
  | "zeit_start"
  | "zeit_stop"
  | "termin"
  | "rechnung_status"
  | "system"
  | "unterschrift"
  | "eingangsrechnung_status"
  | "formular"
  | "leistung";

export interface VorgangEvent {
  id: number;
  vorgang_id: string;
  event_type: VorgangEventType;
  author_user_id: string | null;
  is_system: boolean;
  kundensichtbar: boolean;
  body: string | null;
  payload: Record<string, unknown>;
  ref_entity_type: string | null;
  ref_entity_id: string | null;
  client_uuid: string | null;
  created_at: string;
  foto_url: string | null;
  foto_thumbnail_url: string | null;
  unterschrift_url: string | null;
  dokument_url: string | null;
  dokument_dateiname: string | null;
}

export interface Tag {
  id: string;
  label: string;
  farbe: string | null;
  system_tag: boolean;
  created_at: string;
  updated_at: string;
}

export type TagEntityType = "kunde" | "anlage" | "vorgang" | "material";

export interface TagAssignment {
  tag_id: string;
  entity_type: TagEntityType;
  entity_id: string;
  created_at: string;
}

// --- Social-UX (Phase 3) -------------------------------------------------

export interface FeedCard {
  id: string;
  vorgangsnummer: string;
  titel: string;
  kunde_name: string;
  anlage_kurzadresse: string | null;
  anlage_bezeichnung: string | null;
  standort_bezeichnung: string | null;
  ersteller_name: string | null;
  status: VorgangStatus;
  leistungstyp: Leistungstyp;
  abrechnungsart: VorgangAbrechnungsart;
  prioritaet: number;
  faelligkeit_am: string | null;
  last_activity_at: string;
  letztes_event_vorschau: string | null;
  tags: string[];
  timer_laeuft: boolean;
  dauerauftrag_id: string | null;
  geo_lat: number | null;
  geo_lng: number | null;
  zugewiesener_name: string | null;
}

export interface FeedResponse {
  items: FeedCard[];
  next_cursor: string | null;
}

export interface StoryItem {
  titel: string;
  subtitel: string | null;
  ampel: "gruen" | "gelb" | "rot" | null;
  ziel_typ: "vorgang" | "anlage" | "pruefmittel";
  ziel_id: string;
}

export interface StoriesResponse {
  heute: StoryItem[];
  fristen: StoryItem[];
  wartet_kunde: StoryItem[];
}

export type SearchKategorie = "kunde" | "anlage" | "vorgang" | "tag";

export interface SearchHit {
  kategorie: SearchKategorie;
  id: string;
  titel: string;
  subtitel: string | null;
}

export interface SearchResponse {
  treffer: SearchHit[];
}

export type NotificationTyp = "mention" | "frist" | "zuweisung" | "angebot";

export interface NotificationEntry {
  id: number;
  typ: NotificationTyp;
  titel: string;
  ref_entity_type: string | null;
  ref_entity_id: string | null;
  gelesen_am: string | null;
  created_at: string;
}

export interface KundeProfil extends Kunde {
  anlagen: Anlage[];
  vorgaenge: Vorgang[];
  tags: Tag[];
  techniker: User[];
}

export interface TechnikerZuweisungUebersicht {
  techniker: User;
  kunden: Kunde[];
}

// --- Gespeicherte Filter-Vorlagen -----------------------------------------

export type GespeicherterFilterEntitaet =
  | "vorgaenge"
  | "anlagen"
  | "kunden"
  | "standorte"
  | "rechnungen";

export interface GespeicherterFilter {
  id: string;
  entitaet: GespeicherterFilterEntitaet;
  name: string;
  filter_json: Record<string, string>;
  ist_standard: boolean;
  created_at: string;
  updated_at: string;
}

export interface AnlageProfil extends Anlage {
  kunde: Kunde | null;
  vorgaenge: Vorgang[];
  tags: Tag[];
  vorgaenge_nach_status: Record<string, number>;
  zeiterfassung_stunden_gesamt: string;
}

export interface StandortProfil extends Standort {
  kunde: Kunde | null;
  anlagen: Anlage[];
  vorgaenge: Vorgang[];
  vorgaenge_nach_status: Record<string, number>;
}

// --- Dauerauftraege (wiederkehrende Auftraege) ---------------------------

export type DauerauftragModus = "rollierend" | "fest";

export interface DauerauftragZiel {
  id: string;
  anlage_id: string | null;
  naechste_faelligkeit_am: string;
  offener_vorgang_id: string | null;
}

export interface Dauerauftrag {
  id: string;
  kunde_id: string;
  titel: string;
  beschreibung: string | null;
  abrechnungsart: VorgangAbrechnungsart;
  leistungstyp: Leistungstyp;
  intervall_tage: number;
  modus: DauerauftragModus;
  toleranz_frueh_tage: number | null;
  toleranz_spaet_tage: number | null;
  aktiv: boolean;
  created_at: string;
  updated_at: string;
  ziele: DauerauftragZiel[];
  anzahl_ziele: number;
  naechste_faelligkeit_am: string | null;
}

export interface DauerauftragMitVerlauf extends Dauerauftrag {
  vorgaenge: Vorgang[];
}

// --- Feld-Tauglichkeit (Phase 4) -----------------------------------------

// Muss mit ZEITERFASSUNG_KATEGORIEN in backend/app/models/zeiterfassung.py
// uebereinstimmen.
export type ZeiterfassungKategorie =
  | "auftrag"
  | "verwaltung"
  | "fahrzeit"
  | "schulung"
  | "pause"
  | "urlaub"
  | "krankheit"
  | "sonstiges";

export interface Zeiterfassung {
  id: string;
  vorgang_id: string | null;
  // Transient, vom Backend aufgeloest -- siehe _mit_vorgangsnummern in
  // backend/app/api/routes/zeiterfassung.py.
  vorgangsnummer: string | null;
  techniker_id: string;
  start_at: string;
  ende_at: string | null;
  taetigkeit: string | null;
  abrechenbar: boolean;
  kategorie: ZeiterfassungKategorie;
  lv_position_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ZeiterfassungStatistik {
  wochenstunden: string;
  monatsstunden: string;
  jahresstunden: string;
}

// --- Steuerung (Phase 5) --------------------------------------------------

export type TerminStatus = "geplant" | "bestaetigt" | "abgeschlossen" | "abgesagt";

export interface Termin {
  id: string;
  vorgang_id: string;
  techniker_id: string;
  erstellt_von: string;
  titel: string;
  start_at: string;
  ende_at: string;
  status: TerminStatus;
  notiz: string | null;
  fahrzeit_minuten: number | null;
  pause_minuten: number | null;
  created_at: string;
  updated_at: string;
}

export interface TerminWarnung {
  typ: "ueberschneidung" | "fahrzeit";
  meldung: string;
  anderer_termin_id: string;
}

export interface TerminCreateResult {
  termin: Termin;
  warnungen: TerminWarnung[];
}

export type PruefzyklusEinheit = "tag" | "woche" | "monat" | "stunde";

export interface Pruefzyklus {
  id: string;
  anlage_id: string;
  bezeichnung: string;
  intervall_wert: number;
  intervall_einheit: PruefzyklusEinheit;
  letzte_pruefung_am: string | null;
  naechste_pruefung_am: string;
  aktiv: boolean;
  offener_vorgang_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface InventurZyklus {
  id: string;
  lager_id: string;
  intervall_tage: number;
  letzte_inventur_am: string | null;
  naechste_inventur_am: string;
  aktiv: boolean;
  created_at: string;
  updated_at: string;
}

export interface FahrzeugZuweisungUebersicht {
  techniker: User;
  fahrzeug: Anlage | null;
}

export type PruefmittelStatus = "aktiv" | "defekt" | "ausser_betrieb";

export interface Pruefmittel {
  id: string;
  bezeichnung: string;
  seriennummer: string | null;
  zugewiesen_an: string | null;
  kalibrierintervall_monate: number;
  letzte_kalibrierung_am: string | null;
  naechste_kalibrierung_am: string;
  status: PruefmittelStatus;
  created_at: string;
  updated_at: string;
}

// --- Geschäftsprozesse (Phase 6) ------------------------------------------

export type MangelSchweregrad = "kritisch" | "hoch" | "mittel" | "niedrig";
export type MangelStatus = "offen" | "in_angebot" | "in_bearbeitung" | "behoben" | "abgelehnt";

export interface Mangel {
  id: string;
  vorgang_id: string;
  anlage_id: string | null;
  beschreibung: string;
  schweregrad: MangelSchweregrad;
  status: MangelStatus;
  gemeldet_von: string;
  angebot_id: string | null;
  reparatur_vorgang_id: string | null;
  behoben_am: string | null;
  created_at: string;
  updated_at: string;
}

export type AngebotStatus = "entwurf" | "versendet" | "angenommen" | "abgelehnt";
export type AngebotPositionstyp = "material" | "arbeitszeit";

export interface AngebotPosition {
  id: string;
  position: number;
  artikelnummer: string | null;
  beschreibung: string;
  menge: string;
  einheit: string;
  einzelpreis: string;
  positionstyp: AngebotPositionstyp;
  gesamt: string;
}

export interface Angebot {
  id: string;
  kunde_id: string;
  vorgang_id: string | null;
  angebotsnummer: string;
  status: AngebotStatus;
  mwst_satz: string;
  gueltig_bis: string | null;
  erstellt_von: string;
  versendet_am: string | null;
  angenommen_am: string | null;
  abgelehnt_am: string | null;
  created_at: string;
  updated_at: string;
  positionen: AngebotPosition[];
  gesamt_netto: string;
  gesamt_brutto: string;
}

export type RechnungStatus = "entwurf" | "versendet" | "teilweise_bezahlt" | "bezahlt" | "storniert";
export type RechnungZahlungsart = "ueberweisung" | "bar" | "karte" | "lastschrift" | "sonstiges";

export interface RechnungPosition {
  id: string;
  position: number;
  beschreibung: string;
  menge: string;
  einheit: string;
  einzelpreis: string;
  gesamt: string;
}

// Vom Backend bei jedem Aufruf frisch aus Material-Verwendungen und
// Zeiterfassung des verknuepften Vorgangs berechnet -- kein persistiertes
// Objekt, daher keine id.
export interface RechnungPositionVorschlag {
  quelle: "material" | "zeit" | "leistung";
  beschreibung: string;
  menge: string;
  einheit: string;
  einzelpreis: string;
}

export interface RechnungZahlung {
  id: string;
  betrag: string;
  datum: string;
  zahlungsart: RechnungZahlungsart | null;
  notiz: string | null;
  storniert_zahlung_id: string | null;
  erstellt_von: string;
  created_at: string;
}

export interface RechnungZahlungCreate {
  betrag: string;
  datum?: string;
  zahlungsart?: RechnungZahlungsart;
  notiz?: string;
}

export interface Rechnung {
  id: string;
  kunde_id: string;
  vorgang_id: string | null;
  rechnungsnummer: string;
  betrag_netto: string;
  mwst_satz: string;
  status: RechnungStatus;
  faellig_am: string | null;
  leistungsdatum: string | null;
  ist_storno: boolean;
  storniert_rechnung_id: string | null;
  erstellt_von: string;
  versendet_am: string | null;
  bezahlt_am: string | null;
  mahnstufe: number;
  letzte_mahnung_am: string | null;
  created_at: string;
  updated_at: string;
  positionen: RechnungPosition[];
  betrag_brutto: string;
  ist_ueberfaellig: boolean;
  tage_ueberfaellig: number;
  zahlungen: RechnungZahlung[];
  bezahlter_betrag: string;
  offener_betrag: string;
  // Nur gesetzt, wenn beim Versand ein ZUGFeRD-Hybrid-PDF archiviert wurde.
  xml_object_key: string | null;
}

export interface RechnungListe {
  eintraege: Rechnung[];
  gesamt_anzahl: number;
  summe_netto: string;
  summe_brutto: string;
  summe_offen: string;
}

export interface RechnungenFilter {
  kunde_id?: string;
  vorgang_id?: string;
  status?: RechnungStatus[];
  q?: string;
  von?: string;
  bis?: string;
  faellig_von?: string;
  faellig_bis?: string;
  betrag_von?: string;
  betrag_bis?: string;
  nur_offen?: boolean;
  nur_ueberfaellig?: boolean;
  sort?: string;
  limit?: number;
  offset?: number;
}

export type EingangsrechnungStatus = "entwurf" | "offen" | "bezahlt" | "storniert";
export type EingangsrechnungKategorie =
  | "wareneinkauf"
  | "betriebskosten"
  | "miete"
  | "personal"
  | "fahrzeug"
  | "versicherung"
  | "sonstiges";

export interface EingangsrechnungPosition {
  id: string;
  position: number;
  beschreibung: string;
  menge: string;
  einheit: string;
  einzelpreis: string;
  gesamt: string;
}

export interface EingangsrechnungZahlung {
  id: string;
  betrag: string;
  datum: string;
  erstellt_von: string;
  created_at: string;
}

export interface Eingangsrechnung {
  id: string;
  lieferant_id: string | null;
  lieferant_name: string;
  vorgang_id: string | null;
  rechnungsnummer_lieferant: string;
  rechnungsdatum: string;
  eingegangen_am: string;
  faellig_am: string | null;
  betrag_netto: string;
  mwst_satz: string;
  skonto_prozent: string | null;
  skonto_tage: number | null;
  skonto_frist: string | null;
  skonto_betrag: string | null;
  kategorie: EingangsrechnungKategorie | null;
  status: EingangsrechnungStatus;
  bezahlt_am: string | null;
  beleg_object_key: string | null;
  notiz: string | null;
  erstellt_von: string | null;
  email_absender: string | null;
  email_betreff: string | null;
  created_at: string;
  updated_at: string;
  zahlungen: EingangsrechnungZahlung[];
  bezahlter_betrag: string;
  offener_betrag: string;
  positionen: EingangsrechnungPosition[];
  betrag_brutto: string;
}

export interface EingangsrechnungBelegUrl {
  url: string | null;
}

// --- Ausbau (Phase 7) -----------------------------------------------------

export interface Highlight {
  id: string;
  vorgang_event_id: number;
  titel: string | null;
  erstellt_von: string;
  created_at: string;
  vorgang_id: string;
  vorgangsnummer: string;
  vorgang_titel: string;
  foto_url: string | null;
  foto_thumbnail_url: string | null;
}

export interface MaterialBestand {
  lager_id: string;
  lager_bezeichnung: string;
  menge: string;
}

export interface Material {
  id: string;
  bezeichnung: string;
  einheit: string;
  mindestbestand: string;
  einzelpreis: string | null;
  lieferant_id: string | null;
  artikelnummer: string | null;
  bestell_url: string | null;
  created_at: string;
  updated_at: string;
  bestand_gesamt: string;
  bestaende: MaterialBestand[];
  tag_ids: string[];
}

export interface MaterialVerwendung {
  id: string;
  material_id: string;
  lager_id: string;
  vorgang_id: string;
  menge: string;
  verwendet_von: string;
  created_at: string;
}

export interface MaterialVerwendungMitDetails extends MaterialVerwendung {
  material_bezeichnung: string;
  material_einheit: string;
}

// --- Leistungsverzeichnis (LV) ---------------------------------------------

export interface LeistungsverzeichnisPosition {
  id: string;
  kunde_id: string;
  bezeichnung: string;
  einheit: string;
  einzelpreis: string;
  ist_stundensatz: boolean;
  notiz: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeistungsverzeichnisVerwendung {
  id: string;
  lv_position_id: string;
  vorgang_id: string;
  menge: string;
  verwendet_von: string;
  created_at: string;
}

export interface LeistungsverzeichnisVerwendungMitDetails extends LeistungsverzeichnisVerwendung {
  lv_bezeichnung: string;
  lv_einheit: string;
  lv_einzelpreis: string;
}

// --- Partner/Nachunternehmer -----------------------------------------------

export interface Partner {
  id: string;
  name: string;
  gewerk: string | null;
  ansprechpartner: Ansprechpartner[];
  telefon: string | null;
  email: string | null;
  adresse: Adresse | null;
  notiz: string | null;
  aktiv: boolean;
  created_at: string;
  updated_at: string;
}

export type PartnerNachweisTyp =
  | "freistellungsbescheinigung"
  | "haftpflichtversicherung"
  | "gewerbeanmeldung"
  | "handwerksrolle"
  | "avv_dsgvo"
  | "sonstiges";

export interface PartnerNachweis {
  id: string;
  partner_id: string;
  typ: PartnerNachweisTyp;
  gueltig_bis: string | null;
  dokument_s3_key: string | null;
  notiz: string | null;
  abgelaufen: boolean;
  created_at: string;
  updated_at: string;
}

export type PartnerFreigabeStatus = "vorgeschlagen" | "angenommen" | "abgelehnt";

export interface VorgangPartnerZuweisungResponse {
  vorgang_id: string;
  partner_id: string | null;
  partner_freigabe_status: PartnerFreigabeStatus | null;
  freistellungsbescheinigung_warnung: boolean;
}

export type MaterialBewegungTyp = "eingang" | "umlagerung" | "verwendung" | "korrektur";

export interface MaterialBewegung {
  id: string;
  material_id: string;
  typ: MaterialBewegungTyp;
  von_lager_id: string | null;
  nach_lager_id: string | null;
  menge: string;
  vorgang_id: string | null;
  erstellt_von: string;
  created_at: string;
}

export interface Lieferant {
  id: string;
  name: string;
  email: string | null;
  telefon: string | null;
  notiz: string | null;
  created_at: string;
  updated_at: string;
}

export type MaterialBedarfZweck = "bestellung" | "angebot";
export type MaterialBedarfStatus =
  | "offen"
  | "bestellt"
  | "in_angebot"
  | "erhalten"
  | "storniert"
  | "uebertragen";

export interface MaterialBedarf {
  id: string;
  material_id: string;
  vorgang_id: string;
  menge: string;
  notiz: string | null;
  zweck: MaterialBedarfZweck;
  status: MaterialBedarfStatus;
  bestellung_id: string | null;
  angebot_id: string | null;
  erstellt_von: string;
  uebernommen_von_id: string | null;
  created_at: string;
}

export interface MaterialBedarfMitDetails extends MaterialBedarf {
  material_bezeichnung: string;
  material_einheit: string;
  vorgang_titel: string;
  vorgang_vorgangsnummer: string;
  kunde_name: string;
}

export type BestellungStatus = "entwurf" | "bestellt" | "eingegangen";

export interface BestellungPosition {
  id: string;
  material_id: string;
  position: number;
  beschreibung: string;
  menge: string;
  einheit: string;
  einzelpreis: string;
}

export interface Bestellung {
  id: string;
  lieferant_id: string | null;
  bestellnummer: string;
  status: BestellungStatus;
  notiz: string | null;
  erstellt_von: string;
  created_at: string;
  updated_at: string;
  positionen: BestellungPosition[];
}

export interface Insights {
  vorgaenge_nach_status: Record<string, number>;
  offene_rechnungssumme: string;
  offene_verbindlichkeiten: string;
  angebote_versendet: number;
  angebote_angenommen: number;
  angebote_annahmequote: number | null;
  techniker_auslastung: { techniker_id: string; name: string; stunden_diese_woche: string }[];
}

// --- Kundenportal (Phase 7) ------------------------------------------------

export interface CurrentKunde {
  zugang_id: string;
  kunde_id: string;
  kunde_name: string;
  name: string;
  email: string;
}

export interface KundenportalZugang {
  id: string;
  kunde_id: string;
  email: string;
  name: string;
  aktiv: boolean;
  created_at: string;
  updated_at: string;
}

export interface KundenportalLinkInfo {
  kunde_name: string;
  mandant_name: string;
  hat_logo: boolean;
}

export interface KundeLogoUrl {
  url: string | null;
}

// --- Account-Typen (frei vom mandant_admin definierbare Rollen) ------------

export type RechteBereich =
  | "vorgaenge"
  | "kunden"
  | "material"
  | "dispo"
  | "abrechnung"
  | "statistik"
  | "mitarbeiterverwaltung"
  | "formulare"
  | "partner";
export type RechteAktion = "sehen" | "erstellen" | "bearbeiten" | "loeschen";

export interface RechteMatrixEintrag {
  bereich: RechteBereich;
  aktion: RechteAktion;
  erlaubt: boolean;
}

export interface AccountTyp {
  id: string;
  name: string;
  icon: string | null;
  farbe: string | null;
  nur_zugewiesene_kunden: boolean;
  darf_vorgaenge_selbst_uebernehmen: boolean;
  reihenfolge: number;
  anzahl_nutzer: number;
}

export interface AccountTypCreate {
  name: string;
  icon?: string | null;
  farbe?: string | null;
  nur_zugewiesene_kunden?: boolean;
  darf_vorgaenge_selbst_uebernehmen?: boolean;
}

export interface AccountTypUpdate {
  name?: string;
  icon?: string | null;
  farbe?: string | null;
  nur_zugewiesene_kunden?: boolean;
  darf_vorgaenge_selbst_uebernehmen?: boolean;
  reihenfolge?: number;
}

// --- Mandant-Einstellungen (Nacharbeit) -------------------------------------

export interface MandantFirmendaten {
  adresse?: { strasse?: string; plz?: string; ort?: string; land?: string };
  telefon?: string;
  email?: string;
  website?: string;
  bank_name?: string;
  iban?: string;
  bic?: string;
  handelsregister?: string;
  geschaeftsfuehrung?: string;
  ust_idnr?: string;
  steuernummer?: string;
  // Kleinunternehmer nach §19 UStG: Rechnungs-PDF weist dann keine USt.
  // aus und zeigt statt der Summenzeilen den gesetzlichen Hinweistext.
  ist_kleinunternehmer?: boolean;
  // Je Mahnstufe: automatischer E-Mail-Versand an den Kunden statt nur
  // interner Benachrichtigung. Standard (fehlender Key) ist "aus".
  mahnung_1_automatisch?: boolean;
  mahnung_2_automatisch?: boolean;
  mahnung_3_automatisch?: boolean;
  // ZUGFeRD-Hybrid-PDF beim Rechnungsversand erzeugen, sobald alle
  // EN16931-Pflichtangaben vorhanden sind -- sonst stiller Fallback auf ein
  // normales PDF (siehe e_invoice_service.pruefe_en16931_vollstaendigkeit).
  e_rechnung_aktiv?: boolean;
}

export interface MandantEinstellungen {
  scheduler_stunde_utc: number | null;
  effektive_scheduler_stunde_utc: number;
  wiedervorlage_standard_tage: number | null;
  effektive_wiedervorlage_standard_tage: number;
  firmendaten: MandantFirmendaten;
  logo_object_key: string | null;
}

export interface MandantLogoUrl {
  url: string | null;
}

// --- Mandant-Integrationen (Nacharbeit) -------------------------------------

export interface MandantIntegration {
  id: string;
  mandant_id: string;
  typ: string;
  config: Record<string, unknown>;
  aktiv: boolean;
  hat_secret: boolean;
  created_at: string;
  updated_at: string;
}

// --- Plattform-Integrationen (globaler Mailversand-Fallback) ---------------

export interface PlattformIntegration {
  id: string;
  typ: string;
  config: Record<string, unknown>;
  aktiv: boolean;
  hat_secret: boolean;
  created_at: string;
  updated_at: string;
}

// --- Postfach (persoenlicher IMAP/SMTP-Mailclient) --------------------------

export type MailVerschluesselung = "ssl" | "starttls" | "keine";

export interface MailAccount {
  id: string;
  name: string;
  email_adresse: string;
  imap_host: string;
  imap_port: number;
  imap_verschluesselung: MailVerschluesselung;
  imap_benutzername: string;
  smtp_host: string;
  smtp_port: number;
  smtp_verschluesselung: MailVerschluesselung;
  smtp_benutzername: string;
  signatur: string | null;
  aktiv: boolean;
  letzter_sync_am: string | null;
  letzter_sync_fehler: string | null;
  created_at: string;
  updated_at: string;
}

export interface MailAccountVerbindungTest {
  imap_host: string;
  imap_port: number;
  imap_verschluesselung: MailVerschluesselung;
  imap_benutzername: string;
  smtp_host: string;
  smtp_port: number;
  smtp_verschluesselung: MailVerschluesselung;
  smtp_benutzername: string;
  passwort: string;
}

export interface MailFolder {
  id: string;
  imap_name: string;
  anzeigename: string;
  sortierung: number;
  letzter_sync_am: string | null;
}

export interface MailAttachment {
  id: string;
  dateiname: string;
  mimetype: string;
  groesse_bytes: number;
  eingebettet: boolean;
}

export interface MailMessageListItem {
  id: string;
  folder_id: string;
  von_name: string | null;
  von_adresse: string | null;
  betreff: string;
  ausschnitt: string;
  datum: string | null;
  gelesen: boolean;
  hat_anhang: boolean;
}

export interface MailMessageListResponse {
  items: MailMessageListItem[];
  next_cursor: string | null;
}

export interface MailMessageDetail {
  id: string;
  folder_id: string;
  von_name: string | null;
  von_adresse: string | null;
  an: string[];
  cc: string[];
  betreff: string;
  body_text: string | null;
  body_html: string | null;
  datum: string | null;
  gelesen: boolean;
  message_id_header: string | null;
  anhaenge: MailAttachment[];
}

// --- E-Mail-Versand ----------------------------------------------------------

export type EmailEntityTyp = "kunde" | "vorgang" | "angebot" | "rechnung" | "bestellung";
export type EmailStatus = "gesendet" | "fehler";

export interface EmailLog {
  id: string;
  entity_type: EmailEntityTyp;
  entity_id: string;
  empfaenger: string;
  betreff: string;
  inhalt: string;
  anhang_dateiname: string | null;
  status: EmailStatus;
  fehlermeldung: string | null;
  gesendet_von: string | null;
  created_at: string;
}

// --- Auswertung (USt-VA / DATEV) ---------------------------------------------

export interface UstVaSatzZeile {
  satz: string;
  netto: string;
  steuer: string;
}

export interface UstVaBericht {
  von: string;
  bis: string;
  umsatzsteuer_saetze: UstVaSatzZeile[];
  vorsteuer_saetze: UstVaSatzZeile[];
  summe_umsatzsteuer: string;
  summe_vorsteuer: string;
  zahllast: string;
}

export interface OffenerPostenEintrag {
  id: string;
  nummer: string;
  partner_name: string;
  faellig_am: string | null;
  tage_ueberfaellig: number;
  offener_betrag: string;
}

export interface OffenePostenBucket {
  label: string;
  anzahl: number;
  summe: string;
}

export interface OffenePostenBericht {
  debitoren: OffenerPostenEintrag[];
  kreditoren: OffenerPostenEintrag[];
  summe_debitoren: string;
  summe_kreditoren: string;
  debitoren_buckets: OffenePostenBucket[];
  kreditoren_buckets: OffenePostenBucket[];
}

// --- Formular-Baukasten ------------------------------------------------------

export type FormularfeldTyp =
  | "text"
  | "textarea"
  | "zahl"
  | "datum"
  | "dropdown"
  | "mehrfachauswahl"
  | "ja_nein"
  | "bewertung"
  | "foto"
  | "unterschrift"
  | "gps"
  | "qr_scan"
  | "abschnitt";

// Nutzbare Breite einer A4-Seite in mm -- Obergrenze fuer x_mm + breite_mm
// eines frei positionierten Formularfelds, siehe NUTZBARE_BREITE_MM in
// backend/app/models/formular.py.
export const FORMULAR_NUTZBARE_BREITE_MM = 180;

export type FormularfeldDatenquelle =
  | "vorgang.vorgangsnummer"
  | "vorgang.titel"
  | "vorgang.beschreibung"
  | "vorgang.leistungstyp"
  | "vorgang.faelligkeit_am"
  | "vorgang.adresse"
  | "vorgang.zugewiesener_name"
  | "kunde.kundennummer"
  | "kunde.name"
  | "kunde.adresse"
  | "kunde.ansprechpartner"
  | "anlage.bezeichnung"
  | "anlage.adresse"
  | "anlage.hersteller"
  | "anlage.modell"
  | "anlage.seriennummer"
  | "anlage.anlagentyp"
  | "standort.bezeichnung"
  | "standort.adresse";

export interface Formularfeld {
  id: string;
  feld_typ: FormularfeldTyp;
  label: string;
  hilfetext: string | null;
  pflichtfeld: boolean;
  reihenfolge: number;
  optionen: Record<string, unknown>;
  seite: number;
  x_mm: number;
  y_mm: number;
  breite_mm: number;
  hoehe_mm: number;
  datenquelle: FormularfeldDatenquelle | null;
}

export interface FormularfeldPosition {
  id: string;
  seite: number;
  x_mm: number;
  y_mm: number;
  breite_mm: number;
  hoehe_mm: number;
}

export interface FormularAuftragstypZuordnung {
  id: string;
  leistungstyp: Leistungstyp;
  pflicht_vor_abschluss: boolean;
}

export interface Formular {
  id: string;
  name: string;
  beschreibung: string | null;
  aktiv: boolean;
  erstellt_von: string | null;
  anzahl_seiten: number;
  snap_mm: number | null;
  created_at: string;
  updated_at: string;
  felder: Formularfeld[];
  zuordnungen: FormularAuftragstypZuordnung[];
}

export interface FormularVerfuegbar {
  id: string;
  name: string;
  beschreibung: string | null;
  pflicht_vor_abschluss: boolean;
}

export interface VorgangFormular {
  id: string;
  vorgang_id: string;
  formular_id: string;
  formular_snapshot: {
    snapshot_version?: number;
    name: string;
    anzahl_seiten?: number;
    felder: Formularfeld[];
  };
  antworten: Record<string, unknown>;
  status: "offen" | "abgeschlossen";
  ausgefuellt_von: string | null;
  kundensichtbar: boolean;
  abgeschlossen_am: string | null;
  created_at: string;
  updated_at: string;
}

// --- Boards (Miro-artiges Whiteboard, Office) -----------------------------

export type BoardTyp = "frei" | "bauplanung" | "prozess";

// inhalt_json ist bewusst lose typisiert (Record statt festem Schema): der
// tatsaechliche Node-/Edge-Aufbau folgt @xyflow/react's eigenen Node<T>/
// Edge<T>-Typen aus office/boards/, nicht diesem API-Typ -- hier zaehlt nur,
// dass es ein JSON-Objekt ist, das unveraendert durchgereicht wird.
export interface Board {
  id: string;
  name: string;
  board_typ: BoardTyp;
  inhalt_json: Record<string, unknown>;
  hintergrund_object_key: string | null;
  erstellt_von: string | null;
  created_at: string;
  updated_at: string;
}

export interface BoardListItem {
  id: string;
  name: string;
  board_typ: BoardTyp;
  erstellt_von: string | null;
  created_at: string;
  updated_at: string;
}

export interface BoardHintergrundUrl {
  url: string | null;
}

export interface BoardAnhangUpload {
  object_key: string;
  url: string;
  dateiname: string;
}

export interface BoardAnhangUrl {
  url: string;
}
