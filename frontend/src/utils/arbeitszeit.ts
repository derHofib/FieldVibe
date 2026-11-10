import { SOLL_WOCHENTAG_FELDER, type Bundesland, type SaldoTag } from "../types";
import { formatStundenAlsHHMM } from "./duration";

export const BUNDESLAND_LABEL: Record<Bundesland, string> = {
  BW: "Baden-Württemberg",
  BY: "Bayern",
  BE: "Berlin",
  BB: "Brandenburg",
  HB: "Bremen",
  HH: "Hamburg",
  HE: "Hessen",
  MV: "Mecklenburg-Vorpommern",
  NI: "Niedersachsen",
  NW: "Nordrhein-Westfalen",
  RP: "Rheinland-Pfalz",
  SL: "Saarland",
  SN: "Sachsen",
  ST: "Sachsen-Anhalt",
  SH: "Schleswig-Holstein",
  TH: "Thüringen",
};

/** Stundenwert vom Backend (String mit Punkt) oder aus einem Eingabefeld
 * (Komma erlaubt); ungültig -> 0. */
export function parseStunden(wert: string | number | null | undefined): number {
  if (typeof wert === "number") return Number.isFinite(wert) ? wert : 0;
  const n = Number((wert ?? "").trim().replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

/** Saldo mit Vorzeichen und H:MM, z. B. "+1:30" / "−0:45". Null (nach
 * Minutenrundung) bekommt kein Vorzeichen, sonst stünde dort "−0:00". */
export function formatSaldo(stunden: string | number): string {
  const wert = parseStunden(stunden);
  const minuten = Math.round(Math.abs(wert) * 60);
  if (minuten === 0) return "0:00";
  return `${wert < 0 ? "−" : "+"}${formatStundenAlsHHMM(minuten / 60)}`;
}

export type SaldoTon = "plus" | "minus" | "null";

export function saldoTon(stunden: string | number): SaldoTon {
  const minuten = Math.round(parseStunden(stunden) * 60);
  return minuten > 0 ? "plus" : minuten < 0 ? "minus" : "null";
}

export const SALDO_TON_KLASSE: Record<SaldoTon, string> = {
  plus: "text-st-erledigt",
  minus: "text-st-fehlt",
  null: "text-label2",
};

/** Obergrenze für die Saldo-Abfrage eines Monats: Zukunftstage haben Soll,
 * aber noch kein Ist und würden den Saldo ins Minus drücken. null = der
 * Monat liegt komplett in der Zukunft (kein Aufruf nötig). Datumsstrings
 * YYYY-MM-DD sind lexikographisch vergleichbar. */
export function saldoBis(von: string, bis: string, heute: string): string | null {
  if (von > heute) return null;
  return bis < heute ? bis : heute;
}

export function sollWochensumme(
  felder: Record<(typeof SOLL_WOCHENTAG_FELDER)[number], string>,
): number {
  return SOLL_WOCHENTAG_FELDER.reduce((summe, f) => summe + parseStunden(felder[f]), 0);
}

/** Backend erwartet Decimal mit max. 2 Nachkommastellen als String. */
export function stundenFuerApi(eingabe: string): string {
  return parseStunden(eingabe).toFixed(2);
}

export function saldoTageNachDatum(tage: SaldoTag[]): Map<string, SaldoTag> {
  return new Map(tage.map((t) => [t.datum, t]));
}
