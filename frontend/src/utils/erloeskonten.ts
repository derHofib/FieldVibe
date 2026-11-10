import type { MandantFirmendaten } from "../types";

export const ERLOESKONTO_ZEILEN = [
  { schluessel: "S:19.00", label: "19 %", standardKonto: "8400" },
  { schluessel: "S:7.00", label: "7 %", standardKonto: "8300" },
  { schluessel: "Z:0.00", label: "0 % – Photovoltaik (§ 12 Abs. 3 UStG)", standardKonto: null },
  { schluessel: "E:0.00", label: "Steuerfrei", standardKonto: null },
  { schluessel: "AE:0.00", label: "Reverse Charge (§ 13b UStG)", standardKonto: null },
] as const;

export type ErloeskontoSchluessel = (typeof ERLOESKONTO_ZEILEN)[number]["schluessel"];
export type KontenEingabe = Record<ErloeskontoSchluessel, { konto: string; bu: string }>;
export type KontenFehler = Partial<Record<ErloeskontoSchluessel, { konto?: string; bu?: string }>>;

export function leereKonten(): KontenEingabe {
  return Object.fromEntries(ERLOESKONTO_ZEILEN.map((z) => [z.schluessel, { konto: "", bu: "" }])) as KontenEingabe;
}

/** Konten-Tabelle aus den gespeicherten Firmendaten; unbekannte Schlüssel
 * bleiben außen vor (das Backend lehnt sie beim Speichern ohnehin ab). */
export function kontenAusFirmendaten(fd: MandantFirmendaten): KontenEingabe {
  const eingabe = leereKonten();
  const gespeichert = fd.buchhaltung?.erloeskonten ?? {};
  for (const z of ERLOESKONTO_ZEILEN) {
    const eintrag = gespeichert[z.schluessel];
    if (eintrag) eingabe[z.schluessel] = { konto: eintrag.konto ?? "", bu: eintrag.bu ?? "" };
  }
  return eingabe;
}

/** Konto: leer (Zeile nicht belegt) oder 4-8 Ziffern. */
export function validiereKonto(konto: string): string | null {
  const wert = konto.trim();
  if (wert === "") return null;
  return /^\d{4,8}$/.test(wert) ? null : "Konto: 4 bis 8 Ziffern";
}

/** BU-Schlüssel: leer oder 1-3 Ziffern; ohne Konto sinnlos. */
export function validiereBu(bu: string, konto: string): string | null {
  const wert = bu.trim();
  if (wert === "") return null;
  if (!/^\d{1,3}$/.test(wert)) return "BU-Schlüssel: 1 bis 3 Ziffern";
  if (konto.trim() === "") return "BU-Schlüssel braucht ein Konto";
  return null;
}

export function kontenFehler(eingabe: KontenEingabe): KontenFehler {
  const fehler: KontenFehler = {};
  for (const z of ERLOESKONTO_ZEILEN) {
    const { konto, bu } = eingabe[z.schluessel];
    const k = validiereKonto(konto);
    const b = validiereBu(bu, konto);
    if (k || b) fehler[z.schluessel] = { ...(k ? { konto: k } : {}), ...(b ? { bu: b } : {}) };
  }
  return fehler;
}

/** Nur Zeilen mit Konto; leere Zeilen entfallen (kein Eintrag = Standardkonto
 * bzw. DATEV-Export blockiert). */
export function kontenZuPayload(eingabe: KontenEingabe): Record<string, { konto: string; bu: string }> {
  const payload: Record<string, { konto: string; bu: string }> = {};
  for (const z of ERLOESKONTO_ZEILEN) {
    const konto = eingabe[z.schluessel].konto.trim();
    if (konto) payload[z.schluessel] = { konto, bu: eingabe[z.schluessel].bu.trim() };
  }
  return payload;
}

/** Firmendaten für das PATCH: alles Bestehende bleibt, die Konten ersetzen
 * als vollständige Tabelle `buchhaltung.erloeskonten` (das Backend ersetzt
 * `buchhaltung` als Ganzes); weitere Schlüssel unter `buchhaltung` bleiben. */
export function firmendatenMitKonten(fd: MandantFirmendaten, eingabe: KontenEingabe): MandantFirmendaten {
  return { ...fd, buchhaltung: { ...fd.buchhaltung, erloeskonten: kontenZuPayload(eingabe) } };
}
