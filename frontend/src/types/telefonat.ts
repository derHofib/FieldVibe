import type { VorOrtKontaktKurz } from "./vorOrt";

export type TelefonatRichtung = "ausgehend" | "eingehend";
export type TelefonatErgebnis = "erreicht" | "nicht_erreicht" | "mailbox";
export type TelefonatErstelltVia = "app" | "claude";

export interface Telefonat {
  id: string;
  kunde_id: string | null;
  kunde_name: string | null;
  vorgang_id: string | null;
  vorgang_nummer: string | null;
  vorgang_titel: string | null;
  // id aus kunde.ansprechpartner (JSONB), kein FK -- der Ansprechpartner kann inzwischen fehlen.
  ansprechpartner_id: string | null;
  // Alternative zum Ansprechpartner: Person vor Ort (Mieter/in, Hausmeister/in ...).
  vor_ort_kontakt_id?: string | null;
  vor_ort_kontakt?: VorOrtKontaktKurz | null;
  partner_name: string;
  partner_nummer: string | null;
  richtung: TelefonatRichtung;
  ergebnis: TelefonatErgebnis;
  erstellt_via: TelefonatErstelltVia;
  beginn: string;
  dauer_sekunden: number | null;
  notiz: string | null;
  rueckruf_am: string | null;
  rueckruf_erledigt_am: string | null;
  zeiterfassung_id: string | null;
  erfasst_von: string;
  erfasst_von_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface TelefonatCreate {
  vorgang_id?: string;
  kunde_id?: string;
  ansprechpartner_id?: string;
  vor_ort_kontakt_id?: string;
  partner_name: string;
  partner_nummer?: string;
  richtung: TelefonatRichtung;
  ergebnis: TelefonatErgebnis;
  beginn: string;
  dauer_sekunden?: number;
  notiz?: string;
  rueckruf_am?: string;
  als_arbeitszeit_buchen?: boolean;
  client_uuid?: string;
}

// vorgang_id/kunde_id sind nach dem Anlegen nicht mehr änderbar.
export interface TelefonatUpdate {
  partner_name?: string;
  partner_nummer?: string | null;
  ansprechpartner_id?: string | null;
  vor_ort_kontakt_id?: string | null;
  richtung?: TelefonatRichtung;
  ergebnis?: TelefonatErgebnis;
  beginn?: string;
  dauer_sekunden?: number | null;
  notiz?: string | null;
  rueckruf_am?: string | null;
  rueckruf_erledigt?: boolean;
}

export interface TelefonatFilter {
  kunde_id?: string;
  vorgang_id?: string;
  rueckruf_offen?: boolean;
  von_mir?: boolean;
  ergebnis?: TelefonatErgebnis;
  seite?: number;
  limit?: number;
}

export interface KontaktverlaufEmail {
  id: string;
  betreff: string;
  empfaenger: string;
  status: string;
  vorgang_id: string | null;
  vorgang_nummer: string | null;
  gesendet_am?: string | null;
  created_at?: string;
}

export type KontaktverlaufEintrag =
  | { art: "telefonat"; zeit: string; telefonat: Telefonat }
  | { art: "email"; zeit: string; email: KontaktverlaufEmail };
