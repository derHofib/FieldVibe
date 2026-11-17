import { OPERATOR_LABEL, operatorenFuer, type FilterBedingung, type FilterFeld, type FilterOperator, type FilterWert } from "./typen";

/** Kompaktes JSON `[[feld,op,wert]]` ohne URL-Kodierung -- für `URLSearchParams.set`, das selbst kodiert. */
export function bedingungenZuJson(b: FilterBedingung[]): string {
  return JSON.stringify(b.map((x) => (x.wert === undefined ? [x.feld, x.op] : [x.feld, x.op, x.wert])));
}

export function bedingungenZuUrl(b: FilterBedingung[]): string {
  return encodeURIComponent(bedingungenZuJson(b));
}

export function wertGueltig(w: unknown): w is FilterWert {
  if (typeof w === "string") return true;
  if (Array.isArray(w)) return w.every((x) => typeof x === "string");
  if (w && typeof w === "object") {
    const o = w as Record<string, unknown>;
    if ("relativ" in o) return typeof o.relativ === "string";
    return Object.values(o).every((v) => v === undefined || typeof v === "string");
  }
  return false;
}

/** Ungültiges wird verworfen statt zu werfen (Links können von Hand verändert sein). Mit `felder` zusätzlich
 * unbekannte Felder und Operatoren, die das Feld nicht anbietet. */
export function bedingungenAusUrl<T = unknown>(s: string | null | undefined, felder?: FilterFeld<T>[]): FilterBedingung[] {
  if (!s) return [];
  let roh: unknown;
  try {
    roh = JSON.parse(s.startsWith("[") ? s : decodeURIComponent(s));
  } catch {
    return [];
  }
  if (!Array.isArray(roh)) return [];
  const nachKey = felder ? new Map(felder.map((f) => [f.key, f])) : null;
  const ergebnis: FilterBedingung[] = [];
  for (const eintrag of roh) {
    if (!Array.isArray(eintrag) || typeof eintrag[0] !== "string" || typeof eintrag[1] !== "string") continue;
    const [feld, op, wert] = eintrag as [string, string, unknown];
    if (!(op in OPERATOR_LABEL)) continue;
    if (wert !== undefined && !wertGueltig(wert)) continue;
    if (nachKey) {
      const f = nachKey.get(feld);
      if (!f || !operatorenFuer(f).includes(op as FilterOperator)) continue;
    }
    ergebnis.push(wert === undefined ? { feld, op: op as FilterOperator } : { feld, op: op as FilterOperator, wert });
  }
  return ergebnis;
}
