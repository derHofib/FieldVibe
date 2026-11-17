import type { Pruefmittel, PruefmittelStatus } from "../types";
import type { IconTone } from "../components/IconBadge";

export const PRUEFMITTEL_STATUS_LABEL: Record<PruefmittelStatus, string> = {
  aktiv: "Aktiv",
  defekt: "Defekt",
  ausser_betrieb: "Außer Betrieb",
};

/** Ab so vielen Tagen vor dem Termin gilt eine Kalibrierung als "bald fällig". */
export const BALD_FAELLIG_TAGE = 30;

export type FaelligkeitsStufe = "ueberfaellig" | "bald" | "ok";

/** Datumsvergleich auf ISO-Strings (YYYY-MM-DD), damit Zeitzonen/Sommerzeit keine Rolle spielen. */
export function faelligkeitsStufe(naechsteIso: string, heuteIso: string, baldIso: string): FaelligkeitsStufe {
  if (naechsteIso < heuteIso) return "ueberfaellig";
  if (naechsteIso <= baldIso) return "bald";
  return "ok";
}

export const FAELLIGKEIT_LABEL: Record<FaelligkeitsStufe, string> = {
  ueberfaellig: "Überfällig",
  bald: "Bald fällig",
  ok: "In Ordnung",
};

export const FAELLIGKEIT_TONE: Record<FaelligkeitsStufe, IconTone> = {
  ueberfaellig: "rose",
  bald: "amber",
  ok: "emerald",
};

export type PruefmittelFaelligFilter = "alle" | FaelligkeitsStufe;

/** Defekte/ausgemusterte Geräte werden nicht kalibriert -- sie fallen aus dem Fälligkeitsfilter,
 * statt als "überfällig" Rauschen zu erzeugen. */
export function filterePruefmittel(
  liste: Pruefmittel[],
  suche: string,
  faellig: PruefmittelFaelligFilter,
  heuteIso: string,
  baldIso: string,
  nutzerName: (id: string | null) => string,
): Pruefmittel[] {
  const q = suche.trim().toLowerCase();
  return liste.filter((p) => {
    if (faellig !== "alle") {
      if (p.status !== "aktiv") return false;
      if (faelligkeitsStufe(p.naechste_kalibrierung_am, heuteIso, baldIso) !== faellig) return false;
    }
    if (!q) return true;
    return [p.bezeichnung, p.seriennummer, nutzerName(p.zugewiesen_an)].some((f) => (f ?? "").toLowerCase().includes(q));
  });
}
