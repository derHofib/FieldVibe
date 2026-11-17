import type { LucideIcon } from "lucide-react";

import type { StatusKey } from "../apple/status";

export type FilterFeldTyp =
  | "text"
  | "auswahl"
  | "verknuepfung"
  | "person"
  | "datum"
  | "zahl"
  | "betrag"
  | "liste"
  | "janein";

export type FilterOperator =
  | "enthaelt"
  | "enthaelt_nicht"
  | "ist"
  | "ist_nicht"
  | "beginnt_mit"
  | "endet_mit"
  | "leer"
  | "nicht_leer"
  | "gleich"
  | "ungleich"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "zwischen"
  | "am"
  | "vor"
  | "nach"
  | "relativ";

export type RelativerZeitraum = "ueberfaellig" | "heute" | "woche" | "naechste_7" | "monat" | `letzte_${number}`;

export type FilterWert = string | string[] | { von?: string; bis?: string } | { relativ: RelativerZeitraum };

export interface FilterBedingung {
  feld: string;
  op: FilterOperator;
  wert?: FilterWert;
}

export interface FilterOption {
  wert: string;
  label: string;
  status?: StatusKey;
}

export interface FilterFeld<T> {
  key: string;
  label: string;
  typ: FilterFeldTyp;
  icon: LucideIcon;
  /** Clientseitige Auswertung; Seiten, die serverseitig filtern, lassen es weg. */
  wert?: (zeile: T) => string | number | boolean | string[] | null | undefined;
  optionen?: FilterOption[];
  /** Einschränkung der Operatoren (z. B. weil das Backend nur "ist" kann). Ohne: alle des Typs. */
  operatoren?: FilterOperator[];
  /** Nur eine Auswahl erlaubt (Backend kann nur einen Wert, z. B. kunde_id). */
  einzelwert?: boolean;
  /** Freitext-Vorschläge im Wert-Schritt (Text). */
  vorschlaege?: string[];
}

export const OPERATOREN_JE_TYP: Record<FilterFeldTyp, FilterOperator[]> = {
  text: ["enthaelt", "enthaelt_nicht", "ist", "ist_nicht", "beginnt_mit", "endet_mit", "leer", "nicht_leer"],
  auswahl: ["ist", "ist_nicht"],
  verknuepfung: ["ist", "ist_nicht", "leer", "nicht_leer"],
  person: ["ist", "ist_nicht", "leer"],
  datum: ["am", "vor", "nach", "zwischen", "relativ", "leer", "nicht_leer"],
  zahl: ["gleich", "ungleich", "gt", "gte", "lt", "lte", "zwischen", "leer"],
  betrag: ["gleich", "ungleich", "gt", "gte", "lt", "lte", "zwischen", "leer"],
  liste: ["enthaelt", "enthaelt_nicht", "leer"],
  janein: ["ist"],
};

export const OPERATOR_LABEL: Record<FilterOperator, string> = {
  enthaelt: "enthält",
  enthaelt_nicht: "enthält nicht",
  ist: "ist",
  ist_nicht: "ist nicht",
  beginnt_mit: "beginnt mit",
  endet_mit: "endet mit",
  leer: "ist leer",
  nicht_leer: "ist nicht leer",
  gleich: "=",
  ungleich: "≠",
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  zwischen: "zwischen",
  am: "am",
  vor: "vor",
  nach: "nach",
  // In der Pille steht der Zeitraum selbst im Wert ("Fällig ist diese Woche").
  relativ: "ist",
};

export const OPERATOREN_OHNE_WERT: FilterOperator[] = ["leer", "nicht_leer"];

export const FILTER_TYP_LABEL: Record<FilterFeldTyp, string> = {
  text: "Text",
  auswahl: "Auswahl",
  verknuepfung: "Verknüpfung",
  person: "Person",
  datum: "Datum",
  zahl: "Zahl",
  betrag: "Betrag",
  liste: "Liste",
  janein: "Ja/Nein",
};

export const RELATIV_LABEL: Record<Exclude<RelativerZeitraum, `letzte_${number}`>, string> = {
  ueberfaellig: "überfällig",
  heute: "heute",
  woche: "diese Woche",
  naechste_7: "nächste 7 Tage",
  monat: "dieser Monat",
};

export function relativLabel(r: RelativerZeitraum): string {
  if (r.startsWith("letzte_")) return `letzte ${r.slice("letzte_".length)} Tage`;
  return RELATIV_LABEL[r as keyof typeof RELATIV_LABEL] ?? r;
}

/** Operatoren, die ein Feld tatsächlich anbietet. */
export function operatorenFuer<T>(feld: FilterFeld<T>): FilterOperator[] {
  const alle = OPERATOREN_JE_TYP[feld.typ];
  return feld.operatoren ? alle.filter((o) => feld.operatoren!.includes(o)) : alle;
}
