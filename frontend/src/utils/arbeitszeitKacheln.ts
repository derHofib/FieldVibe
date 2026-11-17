export type ArbeitszeitKachelId =
  | "ist_monat"
  | "soll_monat"
  | "saldo_monat"
  | "saldo_jahr"
  | "woche"
  | "monat_laufend"
  | "jahr"
  | "urlaub_verbleibend"
  | "urlaub_beantragt"
  | "urlaub_resturlaub"
  | "urlaub_genommen"
  | "urlaub_anspruch"
  | "team";

export interface ArbeitszeitKachelDef {
  id: ArbeitszeitKachelId;
  label: string;
  gruppe: "Arbeitszeit" | "Urlaub" | "Team";
  standard: boolean;
}

// Reihenfolge = Anzeigereihenfolge: Ist/Soll/Saldo zuerst, dann Zeiträume, dann Urlaub.
export const ARBEITSZEIT_KACHELN: ArbeitszeitKachelDef[] = [
  { id: "ist_monat", label: "Ist (Monat)", gruppe: "Arbeitszeit", standard: true },
  { id: "soll_monat", label: "Soll (Monat)", gruppe: "Arbeitszeit", standard: true },
  { id: "saldo_monat", label: "Saldo (Monat)", gruppe: "Arbeitszeit", standard: true },
  { id: "saldo_jahr", label: "Saldo seit Jahresbeginn", gruppe: "Arbeitszeit", standard: true },
  { id: "woche", label: "Diese Woche", gruppe: "Arbeitszeit", standard: true },
  { id: "monat_laufend", label: "Laufender Monat", gruppe: "Arbeitszeit", standard: false },
  { id: "jahr", label: "Dieses Jahr", gruppe: "Arbeitszeit", standard: false },
  { id: "urlaub_verbleibend", label: "Urlaub verbleibend", gruppe: "Urlaub", standard: true },
  { id: "urlaub_beantragt", label: "Urlaub beantragt", gruppe: "Urlaub", standard: true },
  { id: "urlaub_resturlaub", label: "Resturlaub", gruppe: "Urlaub", standard: false },
  { id: "urlaub_genommen", label: "Urlaub genommen", gruppe: "Urlaub", standard: false },
  { id: "urlaub_anspruch", label: "Urlaubsanspruch", gruppe: "Urlaub", standard: false },
  { id: "team", label: "Team-Kennzahlen", gruppe: "Team", standard: true },
];

export function standardKacheln(): Set<ArbeitszeitKachelId> {
  return new Set(ARBEITSZEIT_KACHELN.filter((k) => k.standard).map((k) => k.id));
}

/** Unbekannte IDs (z. B. aus einer älteren Version) werden verworfen; ungültiger
 * oder fehlender Speicherstand ergibt den Default, ein leeres Array bleibt "alles aus". */
export function kachelAuswahlAusSpeicher(roh: string | null): Set<ArbeitszeitKachelId> {
  if (roh === null) return standardKacheln();
  try {
    const wert: unknown = JSON.parse(roh);
    if (!Array.isArray(wert)) return standardKacheln();
    const bekannt = new Set<string>(ARBEITSZEIT_KACHELN.map((k) => k.id));
    return new Set(wert.filter((id): id is ArbeitszeitKachelId => typeof id === "string" && bekannt.has(id)));
  } catch {
    return standardKacheln();
  }
}

export function kachelAuswahlFuerSpeicher(auswahl: ReadonlySet<ArbeitszeitKachelId>): string {
  return JSON.stringify(ARBEITSZEIT_KACHELN.filter((k) => auswahl.has(k.id)).map((k) => k.id));
}

export function kachelUmschalten(
  auswahl: ReadonlySet<ArbeitszeitKachelId>,
  id: ArbeitszeitKachelId,
): Set<ArbeitszeitKachelId> {
  const neu = new Set(auswahl);
  if (neu.has(id)) neu.delete(id);
  else neu.add(id);
  return neu;
}

/** Sichtbare Kacheln in fester Reihenfolge; `verfuegbar` blendet aus, was Recht/Daten
 * gerade nicht hergeben (z. B. Saldo ohne hinterlegte Soll-Zeit). */
export function sichtbareKacheln(
  auswahl: ReadonlySet<ArbeitszeitKachelId>,
  verfuegbar: ReadonlySet<ArbeitszeitKachelId>,
): ArbeitszeitKachelId[] {
  return ARBEITSZEIT_KACHELN.filter((k) => auswahl.has(k.id) && verfuegbar.has(k.id)).map((k) => k.id);
}

export function kachelSpeicherKey(userId: string | undefined): string {
  return `office.arbeitszeit.kacheln.${userId ?? "anon"}`;
}
