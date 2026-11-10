import type { MandantFirmendaten } from "../types";

export const KONTENRAHMEN = ["SKR03", "SKR04"] as const;
export type Kontenrahmen = (typeof KONTENRAHMEN)[number];

export const MONATE = [
  "Januar",
  "Februar",
  "März",
  "April",
  "Mai",
  "Juni",
  "Juli",
  "August",
  "September",
  "Oktober",
  "November",
  "Dezember",
] as const;

/** Formularzustand: Zahlen bleiben als Text, damit Tippen nicht springt. */
export interface DatevEingabe {
  beraterNr: string;
  mandantNr: string;
  wjBeginnMonat: string;
  kontenrahmen: Kontenrahmen;
  sachkontenlaenge: string;
}

export type DatevFehler = Partial<Record<"beraterNr" | "mandantNr" | "sachkontenlaenge", string>>;

export function datevAusFirmendaten(fd: MandantFirmendaten): DatevEingabe {
  const b = fd.buchhaltung ?? {};
  return {
    beraterNr: b.berater_nr != null ? String(b.berater_nr) : "",
    mandantNr: b.mandant_nr != null ? String(b.mandant_nr) : "",
    wjBeginnMonat: String(b.wirtschaftsjahr_beginn_monat ?? 1),
    kontenrahmen: b.kontenrahmen ?? "SKR03",
    sachkontenlaenge: String(b.sachkontenlaenge ?? 4),
  };
}

function ganzzahlFehler(wert: string, name: string, min: number, max: number): string | null {
  const text = wert.trim();
  if (text === "") return null;
  if (!/^\d+$/.test(text)) return `${name}: nur Ziffern`;
  const zahl = Number(text);
  return zahl >= min && zahl <= max ? null : `${name}: ${min} bis ${max}`;
}

/** Wie das Backend (mandant_einstellungen.py): Berater 1001-9999999, Mandant
 * 1-99999, Sachkontenlänge 4-8. Leer ist erlaubt (Export blockiert dann). */
export function datevFehler(eingabe: DatevEingabe): DatevFehler {
  const fehler: DatevFehler = {};
  const berater = ganzzahlFehler(eingabe.beraterNr, "Beraternummer", 1001, 9999999);
  const mandant = ganzzahlFehler(eingabe.mandantNr, "Mandantennummer", 1, 99999);
  const laenge = ganzzahlFehler(eingabe.sachkontenlaenge, "Sachkontenlänge", 4, 8);
  if (berater) fehler.beraterNr = berater;
  if (mandant) fehler.mandantNr = mandant;
  if (laenge || eingabe.sachkontenlaenge.trim() === "") fehler.sachkontenlaenge = laenge ?? "Sachkontenlänge: 4 bis 8";
  return fehler;
}

/** Firmendaten für das PATCH. Das Backend ersetzt `buchhaltung` als Ganzes:
 * die Erlöskonten bleiben erhalten, leere Nummern entfallen. */
export function firmendatenMitDatev(fd: MandantFirmendaten, eingabe: DatevEingabe): MandantFirmendaten {
  const { berater_nr: _b, mandant_nr: _m, ...rest } = fd.buchhaltung ?? {};
  const buchhaltung: NonNullable<MandantFirmendaten["buchhaltung"]> = {
    ...rest,
    wirtschaftsjahr_beginn_monat: Number(eingabe.wjBeginnMonat),
    kontenrahmen: eingabe.kontenrahmen,
    sachkontenlaenge: Number(eingabe.sachkontenlaenge),
  };
  if (eingabe.beraterNr.trim()) buchhaltung.berater_nr = Number(eingabe.beraterNr);
  if (eingabe.mandantNr.trim()) buchhaltung.mandant_nr = Number(eingabe.mandantNr);
  return { ...fd, buchhaltung };
}

/** Nur das Format (5-9 Ziffern): Bereich und Länge hängen an der
 * Sachkontenlänge des Mandanten, die nur der Admin lesen darf -- die genaue
 * Prüfung macht das Backend und liefert die Meldung. Leer ist erlaubt (der
 * Export vergibt dann automatisch eines). */
export function validiereDebitorenkonto(konto: string): string | null {
  const wert = konto.trim();
  if (wert === "") return null;
  return /^\d{5,9}$/.test(wert) ? null : "Debitorenkonto: 5 bis 9 Ziffern";
}

/** Meldung des DATEV-Exports bei fehlender Berater-/Mandantennummer. */
export function istDatevStammdatenFehler(meldung: string | null | undefined): boolean {
  return !!meldung && meldung.includes("DATEV-Stammdaten unvollständig");
}

/** Jede 422-Meldung des Exports, die auf die DATEV-Einstellungen verweist
 * (fehlende Stammdaten, Kontenlänge passt nicht zur Sachkontenlänge). */
export function istDatevEinstellungenFehler(meldung: string | null | undefined): boolean {
  return istDatevStammdatenFehler(meldung) || (!!meldung && meldung.includes("Buchhaltung (DATEV)"));
}

/** Standard-Erlöskonto je Kontenrahmen (Placeholder im Erlöskonten-Formular). */
export function standardErloeskonto(schluessel: string, kontenrahmen: Kontenrahmen): string | null {
  const tabelle: Record<Kontenrahmen, Record<string, string>> = {
    SKR03: { "S:19.00": "8400", "S:7.00": "8300" },
    SKR04: { "S:19.00": "4400", "S:7.00": "4300" },
  };
  return tabelle[kontenrahmen][schluessel] ?? null;
}
