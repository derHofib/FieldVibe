import type { RechnungPosition, RechnungVorgangRef } from "../types";

/** Stunden deutsch mit zwei Nachkommastellen, z. B. "3,50 Std". */
export function formatStunden(wert: string | number): string {
  const zahl = Number(wert);
  const text = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
    Number.isNaN(zahl) ? 0 : zahl,
  );
  return `${text} Std`;
}

/** Decimal-String in ganze Cent -- Summen werden in Cent gerechnet, damit
 * keine Gleitkomma-Rundungsfehler entstehen. */
export function zuCent(wert: string): number {
  const zahl = Number(wert);
  return Number.isNaN(zahl) ? 0 : Math.round(zahl * 100);
}

export function centZuText(cent: number): string {
  return (cent / 100).toFixed(2);
}

export interface PositionsGruppe {
  vorgang: RechnungVorgangRef;
  positionen: RechnungPosition[];
  zwischensumme: string;
}

/** Teilt Positionen in ungruppierte (ohne vorgang_id oder mit unbekanntem
 * Vorgang) und je Vorgang der Rechnung eine Gruppe mit Zwischensumme.
 * Reihenfolge der Gruppen folgt `vorgaenge`; Gruppen ohne Positionen entfallen. */
export function gruppierePositionen(
  positionen: RechnungPosition[],
  vorgaenge: RechnungVorgangRef[],
): { ohneVorgang: RechnungPosition[]; gruppen: PositionsGruppe[] } {
  const bekannt = new Set(vorgaenge.map((v) => v.id));
  const ohneVorgang = positionen.filter((p) => !p.vorgang_id || !bekannt.has(p.vorgang_id));
  const gruppen: PositionsGruppe[] = [];
  for (const vorgang of vorgaenge) {
    const eigene = positionen.filter((p) => p.vorgang_id === vorgang.id);
    if (eigene.length === 0) continue;
    const cent = eigene.reduce((summe, p) => summe + zuCent(p.gesamt), 0);
    gruppen.push({ vorgang, positionen: eigene, zwischensumme: centZuText(cent) });
  }
  return { ohneVorgang, gruppen };
}
