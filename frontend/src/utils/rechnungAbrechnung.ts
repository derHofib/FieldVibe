import type { AbrechenbarerVorgang } from "../types";

/** Stunden deutsch mit zwei Nachkommastellen, z. B. "3,50 Std". */
export function formatStunden(wert: string | number): string {
  const zahl = Number(wert);
  const text = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
    Number.isNaN(zahl) ? 0 : zahl,
  );
  return `${text} Std`;
}

/** Ausgewählte Vorgänge mit Stunden ohne SVS, für die kein (oder ein 0-)
 * Stundensatz eingegeben wurde -- diese würden mit 0 EUR angelegt. */
export function zaehleFehlendeSaetze(
  vorgaenge: AbrechenbarerVorgang[],
  ausgewaehlt: ReadonlySet<string>,
  saetze: Readonly<Record<string, string>>,
): number {
  return vorgaenge.filter(
    (v) =>
      ausgewaehlt.has(v.vorgang_id) &&
      Number(v.stunden_ohne_svs) > 0 &&
      !(Number(saetze[v.vorgang_id] ?? "") > 0),
  ).length;
}
