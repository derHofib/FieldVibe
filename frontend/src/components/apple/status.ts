import type { VorgangStatus } from "../../types";

// Sechs Status-Token (Abschnitt 3.2 des UI-Redesign-Auftrags + zwei
// Erweiterungen "wartet"/"fehlt", siehe docs/ui-redesign/AUDIT.md
// "Statusfarben-Mapping"). "fehlt" ("Material fehlt") ist fuer
// Mangel-Status reserviert, nicht fuer Vorgang.status.
export type StatusKey = "neu" | "geplant" | "arbeit" | "fehlt" | "erledigt" | "wartet";

export const STATUS_LABEL: Record<StatusKey, string> = {
  neu: "Neu",
  geplant: "Geplant",
  arbeit: "In Arbeit",
  fehlt: "Material fehlt",
  erledigt: "Erledigt",
  wartet: "Wartet auf Kunde",
};

// Text+Hintergrund (Pille) je Status-Token, als Tailwind-Utility-Klassen ueber
// die in index.css registrierten st-*-Aliase.
export const STATUS_PILLE_KLASSE: Record<StatusKey, string> = {
  neu: "text-st-neu bg-st-neu-bg",
  geplant: "text-st-geplant bg-st-geplant-bg",
  arbeit: "text-st-arbeit bg-st-arbeit-bg",
  fehlt: "text-st-fehlt bg-st-fehlt-bg",
  erledigt: "text-st-erledigt bg-st-erledigt-bg",
  wartet: "text-st-wartet bg-st-wartet-bg",
};

// Eigenstaendige Kreisfarbe (Abschnitt 3.2, Spalte "Kreis") -- bewusst eine
// andere (kraeftigere) Farbe als der Pillen-Text.
export const STATUS_KREIS_KLASSE: Record<StatusKey, string> = {
  neu: "text-st-neu-dot",
  geplant: "text-st-geplant-dot",
  arbeit: "text-st-arbeit-dot",
  fehlt: "text-st-fehlt-dot",
  erledigt: "text-st-erledigt-dot",
  wartet: "text-st-wartet-dot",
};

/** Vorgang.status (7 echte Werte) -> Status-Token (6 Design-Token). Siehe
 * AUDIT.md fuer die Begruendung des Mappings (abgerechnet/storniert teilen
 * sich bewusst Token mit erledigt/geplant statt eigener Farben). */
export function vorgangStatusZuToken(status: VorgangStatus): StatusKey {
  switch (status) {
    case "neu":
      return "neu";
    case "geplant":
      return "geplant";
    case "in_arbeit":
      return "arbeit";
    case "wartet_kunde":
      return "wartet";
    case "abgeschlossen":
    case "abgerechnet":
      return "erledigt";
    case "storniert":
      return "geplant";
  }
}

// Deutsches Label je echtem Vorgang-Status (weicht bei abgerechnet/storniert
// bewusst vom Token-Label ab, siehe vorgangStatusZuToken).
export const VORGANG_STATUS_LABEL: Record<VorgangStatus, string> = {
  neu: "Neu",
  geplant: "Geplant",
  in_arbeit: "In Arbeit",
  wartet_kunde: "Wartet auf Kunde",
  abgeschlossen: "Erledigt",
  abgerechnet: "Abgerechnet",
  storniert: "Storniert",
};
