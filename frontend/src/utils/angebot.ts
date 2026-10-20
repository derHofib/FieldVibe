import type { StatusKey } from "../components/apple/status";
import type { Angebot, AngebotMwstSatz, AngebotStatus } from "../types";
import { tageZwischen } from "./format";

export const ANGEBOT_STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
  widerrufen: "Widerrufen",
};

export const ANGEBOT_STATUS_TOKEN: Record<AngebotStatus, StatusKey> = {
  entwurf: "neu",
  versendet: "wartet",
  angenommen: "erledigt",
  abgelehnt: "fehlt",
  widerrufen: "arbeit",
};

export const MWST_SAETZE: { wert: AngebotMwstSatz; label: string }[] = [
  { wert: "19", label: "19 %" },
  { wert: "7", label: "7 %" },
  { wert: "0", label: "0 %" },
];

/** Backend liefert "19.00"; null bei einem Satz außerhalb der Auswahl
 * (Altbestand), damit die Auswahl dann nichts vortäuscht. */
export function mwstSatzWert(mwstSatz: string): AngebotMwstSatz | null {
  const zahl = Number(mwstSatz);
  return MWST_SAETZE.find((s) => Number(s.wert) === zahl)?.wert ?? null;
}

/** Neue Reihenfolge der Positions-IDs, wenn die Position an `index` um eine
 * Stelle nach oben (-1) oder unten (+1) rückt. Außerhalb der Liste: unverändert. */
export function verschiebePosition(ids: string[], index: number, richtung: -1 | 1): string[] {
  const ziel = index + richtung;
  if (index < 0 || index >= ids.length || ziel < 0 || ziel >= ids.length) return ids;
  const neu = [...ids];
  [neu[index], neu[ziel]] = [neu[ziel], neu[index]];
  return neu;
}

/** Bis zu so vielen Tagen vor Ablauf weist die Seite auf das Ende der Gültigkeit hin
 * (deckt sich mit dem Vorlauf des Nachfass-Laufs im Backend). */
export const ABLAUF_VORLAUF_TAGE = 2;

export type AblaufAnzeige =
  | { art: "abgelaufen" }
  | { art: "laeuft_bald_ab"; tage: number }
  | { art: "keine" };

/** Ob und wie die Gültigkeit hervorgehoben wird. "Abgelaufen" kommt aus dem
 * Backend (Betriebstag in Europe/Berlin); nur die Vorwarnung rechnet hier,
 * mit dem lokalen Kalendertag `heute` (YYYY-MM-DD). */
export function ablaufAnzeige(
  angebot: Pick<Angebot, "status" | "gueltig_bis" | "ist_abgelaufen">,
  heute: string,
): AblaufAnzeige {
  if (angebot.ist_abgelaufen) return { art: "abgelaufen" };
  if (angebot.status !== "versendet" || !angebot.gueltig_bis) return { art: "keine" };
  const tage = tageZwischen(heute, angebot.gueltig_bis);
  return tage >= 0 && tage <= ABLAUF_VORLAUF_TAGE ? { art: "laeuft_bald_ab", tage } : { art: "keine" };
}

export function ablaufText(anzeige: AblaufAnzeige): string | null {
  if (anzeige.art === "abgelaufen") return "Abgelaufen";
  if (anzeige.art === "laeuft_bald_ab") {
    return anzeige.tage === 0 ? "Läuft heute ab" : anzeige.tage === 1 ? "Läuft morgen ab" : `Läuft in ${anzeige.tage} Tagen ab`;
  }
  return null;
}

export interface PositionEingabe {
  beschreibung: string;
  menge: string;
  einheit: string;
  einzelpreis: string;
}

/** Spiegelt die Prüfung des Backends (Beschreibung/Einheit gefüllt, Menge > 0,
 * Preis >= 0); das Backend bleibt verbindlich. */
export function validierePosition(e: PositionEingabe): string | null {
  if (!e.beschreibung.trim()) return "Beschreibung fehlt";
  if (!e.einheit.trim()) return "Einheit fehlt";
  const menge = Number(e.menge.replace(",", "."));
  if (e.menge.trim() === "" || Number.isNaN(menge) || menge <= 0) return "Menge muss größer als 0 sein";
  const preis = Number(e.einzelpreis.replace(",", "."));
  if (e.einzelpreis.trim() === "" || Number.isNaN(preis) || preis < 0) return "Preis darf nicht negativ sein";
  return null;
}
