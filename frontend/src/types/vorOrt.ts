// "Kontakt vor Ort" = Person auf Seite des Kunden (Mieter/in, Hausmeister/in ...), kein Portal-Nutzer.
export type VorOrtRolle = "mieter" | "eigentuemer" | "bauherr" | "hausmeister" | "nutzer" | "sonstige";

export const VOR_ORT_ROLLEN: VorOrtRolle[] = ["mieter", "eigentuemer", "bauherr", "hausmeister", "nutzer", "sonstige"];

export const VOR_ORT_ROLLE_LABEL: Record<VorOrtRolle, string> = {
  mieter: "Mieter/in",
  eigentuemer: "Eigentümer/in",
  bauherr: "Bauherr/in",
  hausmeister: "Hausmeister/in",
  nutzer: "Nutzer/in",
  sonstige: "Sonstige",
};

export type VorOrtQuelle = "buero" | "kundenportal" | "telefonat";

export interface VorOrtKontakt {
  id: string;
  kunde_id: string;
  standort_id: string | null;
  standort_bezeichnung: string | null;
  /** null nach Anonymisierung (und ohne Namen nur mit Telefon). */
  name: string | null;
  rolle: VorOrtRolle;
  einheit: string | null;
  telefon: string | null;
  telefon2: string | null;
  email: string | null;
  erreichbarkeit: string | null;
  hinweis: string | null;
  quelle: VorOrtQuelle | null;
  letzter_einsatz_am: string | null;
  anonymisiert_am: string | null;
  created_at: string;
  updated_at: string;
  zuordnungen_anzahl: number;
  offene_zuordnungen_anzahl: number;
}

export type VorOrtHerkunft = "vorgang" | "auftrag" | "projekt";

export interface VorOrtKontaktZugeordnet {
  zuordnung_id: string;
  kontakt: VorOrtKontakt;
  ist_hauptkontakt: boolean;
  herkunft: VorOrtHerkunft;
  herkunft_id: string;
  herkunft_titel: string;
}

/** Kurzform für Feed-Karten und Listen. */
export interface VorOrtHauptkontaktKurz {
  name: string | null;
  rolle: VorOrtRolle;
  telefon: string | null;
  einheit: string | null;
}

export interface VorOrtKontaktCreate {
  standort_id?: string | null;
  name?: string | null;
  rolle: VorOrtRolle;
  einheit?: string | null;
  telefon?: string | null;
  telefon2?: string | null;
  email?: string | null;
  erreichbarkeit?: string | null;
  hinweis?: string | null;
}

export type VorOrtKontaktUpdate = Partial<VorOrtKontaktCreate>;

export interface VorOrtZuordnungCreate {
  kontakt_id?: string | null;
  neu?: VorOrtKontaktCreate | null;
  ist_hauptkontakt?: boolean;
}

export type VorOrtZiel = "vorgang" | "auftrag" | "projekt";

export interface VorOrtKontaktFilter {
  standort_id?: string;
  rolle?: VorOrtRolle;
  q?: string;
  mit_anonymisierten?: boolean;
}

export interface StandortKurz {
  id: string;
  bezeichnung: string;
  adresse: { strasse?: string; plz?: string; ort?: string } | null;
}

/** Kontakt, den das Kundenportal mit einer Anfrage mitgibt (max. 5, je Name oder Telefon). */
export interface PortalVorOrtKontaktEingabe {
  name?: string | null;
  rolle: VorOrtRolle;
  telefon?: string | null;
  erreichbarkeit?: string | null;
  hinweis?: string | null;
}

/** Portal-Sicht auf Kontakte des eigenen Vorgangs (ohne E-Mail). */
export interface PortalVorOrtKontakt {
  name: string | null;
  rolle: VorOrtRolle;
  einheit: string | null;
  telefon: string | null;
  erreichbarkeit: string | null;
  hinweis: string | null;
}

/** Partnerportal: nur bei angenommenem Vorgang, keine E-Mail. */
export interface PartnerVorOrtKontakt extends PortalVorOrtKontakt {
  telefon2: string | null;
}

export interface VorOrtKontaktKurz {
  id: string;
  name: string | null;
  rolle: VorOrtRolle;
}

/** Antwort von GET /api/telefonate/nummer-zuordnen?nummer= (null = unbekannte Nummer). */
export interface TelefonNummerZuordnung {
  kunde_id: string;
  kunde_name: string;
  ansprechpartner_id: string | null;
  vor_ort_kontakt_id: string | null;
  offene_vorgaenge: { id: string; vorgangsnummer: string; titel: string }[];
}
