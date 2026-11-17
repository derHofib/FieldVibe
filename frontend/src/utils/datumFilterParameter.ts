import { isoDatum, zeitraumAufloesen } from "../components/filter/auswerten";
import type { FilterBedingung } from "../components/filter/typen";

function tagVerschoben(iso: string, tage: number): string {
  const [j, m, t] = iso.split("-").map(Number);
  return isoDatum(new Date(j, m - 1, t + tage));
}

/** Übersetzt eine Datums-Bedingung in die Server-Parameter `von`/`bis` (beide inklusive).
 * "vor X" heißt bis zum Vortag, "nach X" ab dem Folgetag. */
export function datumZuVonBis(b: FilterBedingung): { von?: string; bis?: string } {
  const w = b.wert;
  if (b.op === "relativ" && w && typeof w === "object" && "relativ" in w) return zeitraumAufloesen(w.relativ);
  if (b.op === "zwischen" && w && typeof w === "object" && !Array.isArray(w) && !("relativ" in w)) {
    return { von: w.von || undefined, bis: w.bis || undefined };
  }
  if (typeof w !== "string" || !w) return {};
  if (b.op === "am") return { von: w, bis: w };
  if (b.op === "vor") return { bis: tagVerschoben(w, -1) };
  if (b.op === "nach") return { von: tagVerschoben(w, 1) };
  return {};
}

/** Wie `datumZuVonBis`, aber ohne leere Schlüssel (für `zuServerParametern`). */
export function datumServerParameter(b: FilterBedingung): Record<string, string> {
  const { von, bis } = datumZuVonBis(b);
  return { ...(von ? { von } : {}), ...(bis ? { bis } : {}) };
}
