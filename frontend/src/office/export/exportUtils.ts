export type ExportArt = "vollexport" | "z3";
export type ExportStatus = "wartend" | "laeuft" | "fertig" | "fehler" | "abgelaufen";

export interface MandantExport {
  id: string;
  art: ExportArt;
  status: ExportStatus;
  parameter: { von?: string; bis?: string };
  angefordert_von: string;
  angefordert_am: string;
  fertig_am: string | null;
  laeuft_ab_am: string | null;
  groesse_bytes: number | null;
  sha256: string | null;
  anzahl_dateien: number | null;
  fehler: string | null;
}

export interface ExportDownload {
  url: string;
  gueltig_bis: string;
  sha256: string | null;
}

export const ART_LABEL: Record<ExportArt, string> = {
  vollexport: "Vollexport",
  z3: "Z3 (Datenträgerüberlassung)",
};

export const STATUS_LABEL: Record<ExportStatus, string> = {
  wartend: "Wartet",
  laeuft: "Läuft",
  fertig: "Fertig",
  fehler: "Fehlgeschlagen",
  abgelaufen: "Abgelaufen",
};

// Farbe nur ueber die Status-Token; das Wort traegt die Bedeutung zusaetzlich.
export const STATUS_KLASSE: Record<ExportStatus, string> = {
  wartend: "bg-st-arbeit-bg text-st-arbeit-text",
  laeuft: "bg-st-arbeit-bg text-st-arbeit-text",
  fertig: "bg-st-erledigt-bg text-st-erledigt",
  fehler: "bg-st-fehlt-bg text-st-fehlt-text",
  abgelaufen: "bg-fill text-label",
};

export function istAktiv(export_: Pick<MandantExport, "status">): boolean {
  return export_.status === "wartend" || export_.status === "laeuft";
}

export function aktiverExportVorhanden(liste: readonly Pick<MandantExport, "status">[]): boolean {
  return liste.some(istAktiv);
}

/** Vorjahr als Standardzeitraum fuer Z3 (typisch angeforderter Pruefzeitraum beginnt mit dem Vorjahr). */
export function standardZeitraum(heute: Date = new Date()): { von: string; bis: string } {
  const jahr = heute.getFullYear() - 1;
  return { von: `${jahr}-01-01`, bis: `${jahr}-12-31` };
}

export function zeitraumGueltig(von: string, bis: string): string | null {
  if (!von || !bis) return "Bitte Zeitraum angeben.";
  if (bis < von) return "„Bis“ darf nicht vor „Von“ liegen.";
  const tage = (Date.parse(bis) - Date.parse(von)) / 86_400_000;
  if (tage > 366 * 5) return "Der Zeitraum darf höchstens fünf Jahre umfassen.";
  return null;
}

export function parameterText(e: Pick<MandantExport, "art" | "parameter">): string {
  if (e.art !== "z3" || !e.parameter.von || !e.parameter.bis) return "";
  const f = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
  return `${f(e.parameter.von)} – ${f(e.parameter.bis)}`;
}

/** Verbleibende Tage bis zum automatischen Entfernen, nie negativ. */
export function resttage(laeuftAb: string | null, jetzt: Date = new Date()): number | null {
  if (!laeuftAb) return null;
  return Math.max(0, Math.ceil((Date.parse(laeuftAb) - jetzt.getTime()) / 86_400_000));
}
