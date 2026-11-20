// Vertrag zu /api/kennzahlen (backend/app/api/routes/kennzahlen.py). Feldnamen
// exakt wie dort, damit Antworten ohne Umbenennung durchgereicht werden.

export type KennzahlEinheit = "anzahl" | "eur" | "tage" | "prozent" | "minuten";
// stand = Momentaufnahme heute, unabhaengig vom Dashboard-Zeitraum.
export type KennzahlArt = "zeitraum" | "stand";
export type KennzahlBereich = "vorgaenge" | "finanzen" | "sales" | "telefonate";
export type Darstellung = "zahl" | "zahl_verlauf" | "saeulen" | "linie" | "balken" | "ring" | "tabelle";
export type WidgetGroesse = "s" | "m" | "l" | "xl";
export type DashboardZeitraum = "woche" | "monat" | "quartal" | "jahr" | "12_monate";

export interface KennzahlGruppierung {
  schluessel: string;
  label: string;
  /** true = Zeitachse (Woche/Monat), sonst Kategorie (Techniker, Kunde ...). */
  zeit: boolean;
}

export interface KennzahlDef {
  schluessel: string;
  titel: string;
  beschreibung: string;
  bereich: KennzahlBereich;
  einheit: KennzahlEinheit;
  art: KennzahlArt;
  /** false bei Durchlaufzeit/Quoten: Teile ergeben keine sinnvolle Summe (kein Ring, kein "Weitere"). */
  summierbar: boolean;
  gruppierungen: KennzahlGruppierung[];
}

export interface KennzahlZeile {
  schluessel: string;
  label: string;
  wert: number | null;
  vorperiode: number | null;
}

export interface KennzahlDaten {
  kennzahl: string;
  einheit: KennzahlEinheit;
  art: KennzahlArt;
  gruppierung: string;
  von: string | null;
  bis: string | null;
  gesamt: number | null;
  vorperiode_gesamt: number | null;
  zeilen: KennzahlZeile[];
  abgeschnitten: boolean;
  datumsbezug: string | null;
}

export interface DashboardWidget {
  id: string;
  kennzahl: string;
  darstellung: Darstellung;
  gruppierung: string | null;
  groesse: WidgetGroesse;
  titel: string | null;
  vergleich: boolean;
}

export interface DashboardLayout {
  zeitraum: DashboardZeitraum;
  widgets: DashboardWidget[];
}

export interface KennzahlenDashboard {
  id: string;
  name: string;
  layout: DashboardLayout;
  fuer_alle: boolean;
  vorlage: string | null;
  sortierung: number;
  eigenes: boolean;
  ersteller_name: string;
  updated_at: string;
}

export interface KennzahlDatenParams {
  kennzahl: string;
  gruppierung?: string;
  von?: string;
  bis?: string;
  vergleich_von?: string;
  vergleich_bis?: string;
}
