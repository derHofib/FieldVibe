import type {
  ZeitplanAntrag,
  ZeitplanAntragArt,
  ZeitplanAntragCreate,
  ZeitplanAntragStatus,
  ZeitplanElement,
} from "../../../types";
import type { StatusKey } from "../../../components/apple/status";
import { addTage, diffTage, formatKurz, formatTag, heuteTag, parseTag } from "./zeitplanLogik";

export const ANTRAG_ART_LABEL: Record<ZeitplanAntragArt, string> = {
  verschieben: "Verschieben",
  dauer_aendern: "Dauer ändern",
  problem: "Problem melden",
};

export const ANTRAG_STATUS_LABEL: Record<ZeitplanAntragStatus, string> = {
  offen: "Offen",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
  zurueckgezogen: "Zurückgezogen",
};

/** Beantragbare Arten je Element -- spiegelt die Server-Regeln: Phasen gar
 * nicht, Meilensteine ohne Dauer, Lieferungen (Datum aus der Bestellung) nur
 * als Problemmeldung. */
export function beantragbareArten(e: Pick<ZeitplanElement, "typ" | "datum_gesperrt">): ZeitplanAntragArt[] {
  if (e.typ === "phase") return [];
  if (e.datum_gesperrt) return ["problem"];
  if (e.typ === "meilenstein") return ["verschieben", "problem"];
  return ["verschieben", "dauer_aendern", "problem"];
}

export interface AntragDaten {
  start: string;
  ende: string;
}

/** Vorbelegung der Datumsfelder aus dem aktuellen Plan (ohne Datum: heute). */
export function antragVorbelegung(e: Pick<ZeitplanElement, "start_am" | "ende_am">, heute: number = heuteTag()): AntragDaten {
  const start = e.start_am ?? formatTag(heute);
  return { start, ende: e.ende_am ?? start };
}

/** Beim Verschieben bleibt die bisherige Dauer: neues Ende = neuer Start + Dauer. */
export function endeNachVerschieben(e: Pick<ZeitplanElement, "start_am" | "ende_am">, neuerStart: string): string {
  if (!e.start_am || !e.ende_am) return neuerStart;
  return addTage(neuerStart, diffTage(e.start_am, e.ende_am));
}

/** Validierung vor dem Absenden; null = ok. */
export function antragFehler(
  e: Pick<ZeitplanElement, "start_am" | "ende_am">,
  art: ZeitplanAntragArt,
  daten: AntragDaten,
  begruendung: string,
): string | null {
  if (!begruendung.trim()) return "Bitte eine Begründung angeben.";
  if (art === "verschieben" && !daten.start) return "Bitte einen Wunsch-Start angeben.";
  if (art === "dauer_aendern") {
    if (!daten.ende) return "Bitte ein Wunsch-Ende angeben.";
    if (e.start_am && daten.ende < e.start_am) return "Das Ende liegt vor dem Start.";
  }
  return null;
}

export function baueAntrag(
  e: Pick<ZeitplanElement, "id" | "typ" | "start_am" | "ende_am">,
  art: ZeitplanAntragArt,
  daten: AntragDaten,
  begruendung: string,
): ZeitplanAntragCreate {
  const body: ZeitplanAntragCreate = { element_id: e.id, art, begruendung: begruendung.trim() };
  if (art === "verschieben") {
    body.gewuenschter_start_am = daten.start;
    body.gewuenschtes_ende_am = e.typ === "meilenstein" ? daten.start : endeNachVerschieben(e, daten.start);
  } else if (art === "dauer_aendern") {
    body.gewuenschtes_ende_am = daten.ende;
  }
  return body;
}

function bereich(start: string | null, ende: string | null): string {
  if (!start && !ende) return "ohne Datum";
  const s = start ?? ende!;
  const e = ende ?? start!;
  return s === e ? formatKurz(parseTag(s)) : `${formatKurz(parseTag(s))} – ${formatKurz(parseTag(e))}`;
}

/** "12.10. – 14.10. → 19.10. – 21.10." bzw. "Problem" ohne Wunschtermine. */
export function antragZeitText(a: ZeitplanAntrag): string {
  if (a.art === "problem") return "Problem gemeldet";
  const aktuell = bereich(a.aktueller_start_am, a.aktuelles_ende_am);
  const wunsch = bereich(a.gewuenschter_start_am ?? a.aktueller_start_am, a.gewuenschtes_ende_am);
  return `${aktuell} → ${wunsch}`;
}

export function offeneAntraege(antraege: ZeitplanAntrag[]): ZeitplanAntrag[] {
  return antraege.filter((a) => a.status === "offen");
}

/** Summe der offenen Anträge über alle Elemente (Badge der Werkzeugleiste). */
export function offeneAntraegeGesamt(elemente: Pick<ZeitplanElement, "offene_antraege">[]): number {
  return elemente.reduce((s, e) => s + (e.offene_antraege ?? 0), 0);
}

/** Status-Token der Pille: offen wartet auf das Büro, angenommen = erledigt, abgelehnt = Fehlt-Rot. */
export const ANTRAG_STATUS_TOKEN: Record<ZeitplanAntragStatus, StatusKey> = {
  offen: "wartet",
  angenommen: "erledigt",
  abgelehnt: "fehlt",
  zurueckgezogen: "geplant",
};
