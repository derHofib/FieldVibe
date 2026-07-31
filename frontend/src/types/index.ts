export type MandantStatus = "aktiv" | "pausiert" | "gekuendigt";
export type Role = "super_admin" | "mandant_admin" | "disponent" | "techniker";

export interface Mandant {
  id: string;
  name: string;
  slug: string;
  branche: string | null;
  status: MandantStatus;
  branding: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: string;
  mandant_id: string | null;
  email: string;
  role: Role;
  name: string;
  avatar_url: string | null;
  aktiv: boolean;
  created_at: string;
  updated_at: string;
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

export interface CurrentUser {
  id: string;
  mandant_id: string | null;
  mandant_name: string | null;
  role: Role;
  name: string;
  email: string;
  impersonated_by: string | null;
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
  created_at: string;
  updated_at: string;
}

export type AnlagenObjekttyp = "kundenanlage" | "fahrzeug" | "lager" | "baustelle";

export interface Anlage {
  id: string;
  kunde_id: string | null;
  objekttyp: AnlagenObjekttyp;
  bezeichnung: string;
  adresse: Adresse;
  anlagentyp: string | null;
  qr_code: string | null;
  stammdaten: Record<string, unknown>;
  geo_lat: number | null;
  geo_lng: number | null;
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
  vertrag_id: string | null;
  parent_vorgang_id: string | null;
  dauerauftrag_id: string | null;
  titel: string;
  beschreibung: string | null;
  abrechnungsart: VorgangAbrechnungsart;
  leistungstyp: Leistungstyp;
  status: VorgangStatus;
  prioritaet: number;
  last_activity_at: string;
  abgeschlossen_am: string | null;
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
  | "unterschrift";

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
}

export interface Tag {
  id: string;
  label: string;
  farbe: string | null;
  system_tag: boolean;
  created_at: string;
  updated_at: string;
}

// --- Social-UX (Phase 3) -------------------------------------------------

export interface FeedCard {
  id: string;
  vorgangsnummer: string;
  titel: string;
  kunde_name: string;
  anlage_kurzadresse: string | null;
  status: VorgangStatus;
  leistungstyp: Leistungstyp;
  abrechnungsart: VorgangAbrechnungsart;
  prioritaet: number;
  last_activity_at: string;
  letztes_event_vorschau: string | null;
  tags: string[];
  timer_laeuft: boolean;
  dauerauftrag_id: string | null;
}

export interface FeedResponse {
  items: FeedCard[];
  next_cursor: string | null;
}

export interface StoryItem {
  titel: string;
  subtitel: string | null;
  ampel: "gruen" | "gelb" | "rot" | null;
  ziel_typ: "vorgang" | "anlage" | "pruefmittel" | "material";
  ziel_id: string;
}

export interface StoriesResponse {
  heute: StoryItem[];
  fristen: StoryItem[];
  wartet_kunde: StoryItem[];
  material: StoryItem[];
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

export interface AnlageProfil extends Anlage {
  kunde: Kunde | null;
  vorgaenge: Vorgang[];
  tags: Tag[];
  vorgaenge_nach_status: Record<string, number>;
  zeiterfassung_stunden_gesamt: string;
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

export interface Zeiterfassung {
  id: string;
  vorgang_id: string;
  techniker_id: string;
  start_at: string;
  ende_at: string | null;
  taetigkeit: string | null;
  abrechenbar: boolean;
  freigegeben: boolean;
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

export interface Pruefzyklus {
  id: string;
  anlage_id: string;
  bezeichnung: string;
  intervall_monate: number;
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

export interface AngebotPosition {
  id: string;
  position: number;
  beschreibung: string;
  menge: string;
  einheit: string;
  einzelpreis: string;
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

export type RechnungStatus = "entwurf" | "versendet" | "bezahlt" | "storniert";

export interface RechnungPosition {
  id: string;
  position: number;
  beschreibung: string;
  menge: string;
  einheit: string;
  einzelpreis: string;
  gesamt: string;
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
  erstellt_von: string;
  versendet_am: string | null;
  bezahlt_am: string | null;
  mahnstufe: number;
  letzte_mahnung_am: string | null;
  created_at: string;
  updated_at: string;
  positionen: RechnungPosition[];
  betrag_brutto: string;
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
  created_at: string;
  updated_at: string;
  bestand_gesamt: string;
  bestaende: MaterialBestand[];
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

export interface Insights {
  vorgaenge_nach_status: Record<string, number>;
  offene_rechnungssumme: string;
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

// --- Mandant-Einstellungen (Nacharbeit) -------------------------------------

export interface MandantEinstellungen {
  scheduler_stunde_utc: number | null;
  effektive_scheduler_stunde_utc: number;
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
