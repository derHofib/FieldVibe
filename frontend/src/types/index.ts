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

export interface Kunde {
  id: string;
  kundennummer: string;
  name: string;
  typ: KundeTyp | null;
  ansprechpartner: unknown[];
  adresse: Record<string, unknown> | null;
  notiz: string | null;
  created_at: string;
  updated_at: string;
}

export interface Anlage {
  id: string;
  kunde_id: string;
  bezeichnung: string;
  adresse: Record<string, unknown>;
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
  | "system";

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
}

export interface AnlageProfil extends Anlage {
  kunde: Kunde;
  vorgaenge: Vorgang[];
  tags: Tag[];
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
