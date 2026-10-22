import type { Adresse } from "../../../types";
import { datumZuIso } from "../../../utils/format";

export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Fuer den Termine-Wochenkalender im Desktop-Layout (layout="dicht") --
// gleiche Rechenlogik wie office/DispoBoardPage.tsx, hier aber lokal
// kopiert statt importiert: dort ist es eine Seiten-lokale Hilfsfunktion,
// kein geteiltes Modul.
export const WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

export function startOfWoche(d: Date): Date {
  const date = new Date(d);
  const tag = date.getDay(); // 0 = Sonntag
  const diffZuMontag = tag === 0 ? -6 : 1 - tag;
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + diffZuMontag);
  return date;
}

export function addTage(d: Date, n: number): Date {
  const date = new Date(d);
  date.setDate(date.getDate() + n);
  return date;
}

export function tagesSchluessel(d: Date): string {
  return datumZuIso(d);
}

export function leereAdresse(adresse: Adresse | null | undefined): { strasse: string; plz: string; ort: string } {
  return { strasse: adresse?.strasse ?? "", plz: adresse?.plz ?? "", ort: adresse?.ort ?? "" };
}

export function adresseAlsZeile(adresse: Adresse | null | undefined): string {
  return [adresse?.strasse, [adresse?.plz, adresse?.ort].filter(Boolean).join(" ")]
    .filter(Boolean)
    .join(", ");
}
