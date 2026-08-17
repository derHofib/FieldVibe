import type { ZeiterfassungKategorie } from "../types";

// Muss mit ZEITERFASSUNG_KATEGORIE_LABEL in backend/app/schemas/zeiterfassung.py
// uebereinstimmen ("auftrag" hat bewusst kein Label -- dort steht die
// Vorgangsnummer statt einer Kategorie-Bezeichnung).
export const ZEITERFASSUNG_KATEGORIE_LABEL: Partial<Record<ZeiterfassungKategorie, string>> = {
  verwaltung: "Verwaltung",
  fahrzeit: "Fahrzeit",
  schulung: "Schulung",
  pause: "Pause",
  urlaub: "Urlaub",
  krankheit: "Krankheit",
  sonstiges: "Sonstiges",
};

// Muss mit ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT in
// backend/app/schemas/zeiterfassung.py uebereinstimmen.
export const ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT: ZeiterfassungKategorie[] = [
  "pause",
  "urlaub",
  "krankheit",
];

export function formatDauer(startAt: string, endeAt: string | null): number {
  if (!endeAt) return 0;
  return (new Date(endeAt).getTime() - new Date(startAt).getTime()) / 1000 / 3600;
}

/** Lokaler Kalendertag (nicht UTC) als sortierbarer YYYY-MM-DD-Schluessel --
 * ein Eintrag, der z.B. um 23:30 Ortszeit beginnt, soll auf DEM Tag
 * gruppiert werden, nicht auf dem naechsten UTC-Tag. */
export function lokalerTag(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function formatUhrzeit(iso: string): string {
  return new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

export function montagDerWoche(datum: Date): Date {
  const tag = datum.getDay();
  const diffZuMontag = tag === 0 ? -6 : 1 - tag;
  const montag = new Date(datum);
  montag.setDate(datum.getDate() + diffZuMontag);
  montag.setHours(0, 0, 0, 0);
  return montag;
}

export function toDateInput(d: Date): string {
  return d.toISOString().slice(0, 10);
}
