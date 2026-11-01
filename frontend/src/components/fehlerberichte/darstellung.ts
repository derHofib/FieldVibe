import type { StatusKey } from "../apple/status";
import type { NetzwerkEintrag } from "../../bugreport/typen";
import type { FehlerberichtArt, FehlerberichtSchweregrad, FehlerberichtStatus } from "../../types";

export const FEHLER_STATUS: FehlerberichtStatus[] = ["neu", "gesichtet", "in_arbeit", "behoben", "abgelehnt", "duplikat"];
export const OFFENE_STATUS: FehlerberichtStatus[] = ["neu", "gesichtet", "in_arbeit"];
export const SCHWEREGRADE: FehlerberichtSchweregrad[] = ["niedrig", "mittel", "hoch", "blockierend"];

export const FEHLER_STATUS_LABEL: Record<FehlerberichtStatus, string> = {
  neu: "Neu",
  gesichtet: "Gesichtet",
  in_arbeit: "In Arbeit",
  behoben: "Behoben",
  abgelehnt: "Abgelehnt",
  duplikat: "Duplikat",
};

export const IDEE_STATUS_LABEL: Record<FehlerberichtStatus, string> = {
  neu: "Neu",
  gesichtet: "Freigegeben",
  in_arbeit: "In Umsetzung",
  behoben: "Umgesetzt",
  abgelehnt: "Abgelehnt",
  duplikat: "Duplikat",
};

export function statusLabel(status: FehlerberichtStatus, art: FehlerberichtArt = "fehler"): string {
  return (art === "idee" ? IDEE_STATUS_LABEL : FEHLER_STATUS_LABEL)[status];
}

// Eigene Farbtoken gibt es fuer Fehlerberichte nicht -- Mapping auf die
// sechs Status-Token; abgelehnt/duplikat teilen sich bewusst das neutrale Grau.
export const FEHLER_STATUS_TOKEN: Record<FehlerberichtStatus, StatusKey> = {
  neu: "neu",
  gesichtet: "wartet",
  in_arbeit: "arbeit",
  behoben: "erledigt",
  abgelehnt: "geplant",
  duplikat: "geplant",
};

export const SCHWEREGRAD_LABEL: Record<FehlerberichtSchweregrad, string> = {
  niedrig: "Niedrig",
  mittel: "Mittel",
  hoch: "Hoch",
  blockierend: "Blockierend",
};

// mittel hat keinen Status-Token (kein Gelb im System) -> neutrale Flaeche.
export const SCHWEREGRAD_KLASSE: Record<FehlerberichtSchweregrad, string> = {
  blockierend: "text-st-fehlt bg-st-fehlt-bg",
  hoch: "text-st-arbeit bg-st-arbeit-bg",
  mittel: "text-label bg-fill2",
  niedrig: "text-st-geplant bg-st-geplant-bg",
};

export function istDringend(schweregrad: FehlerberichtSchweregrad): boolean {
  return schweregrad === "blockierend" || schweregrad === "hoch";
}

export function netzwerkFehlgeschlagen(e: Pick<NetzwerkEintrag, "status" | "fehler">): boolean {
  return e.status >= 400 || !!e.fehler;
}

export function relativeZeit(iso: string, jetzt: number = Date.now()): string {
  const min = Math.floor((jetzt - new Date(iso).getTime()) / 60_000);
  if (min < 60) return min <= 1 ? "gerade eben" : `vor ${min} Min.`;
  const std = Math.floor(min / 60);
  if (std < 24) return `vor ${std} Std.`;
  const tage = Math.floor(std / 24);
  return tage === 1 ? "vor 1 Tag" : `vor ${tage} Tagen`;
}

export function datumZeit(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", { timeZone: "Europe/Berlin" });
}

export function kurzCommit(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 7) : "–";
}

export function istHttpUrl(wert: string): boolean {
  return /^https?:\/\//i.test(wert);
}
