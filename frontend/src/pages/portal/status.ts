import type { AngebotStatus } from "../../types";

// Gemeinsame Quelle fuer PortalAngebotePage (Liste) und
// PortalAngebotDetailPage (Detail) -- vorher zwei identische Kopien, die bei
// einem neuen Status auseinandergelaufen waeren (siehe DESIGN.md-Regel zu
// STATUS_LABEL/STATUS_BADGE fuer Vorgaenge, hier analog fuer Angebote).
export const ANGEBOT_STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

export const ANGEBOT_STATUS_BADGE: Record<AngebotStatus, string> = {
  entwurf: "border border-slate-300 text-slate-500 dark:border-stone-700 dark:text-stone-400",
  versendet: "border border-blue-400 text-blue-700 dark:border-blue-600 dark:text-blue-300",
  angenommen: "border border-green-400 text-green-700 dark:border-green-600 dark:text-green-300",
  abgelehnt: "border border-red-400 text-red-700 dark:border-red-600 dark:text-red-300",
};

// Laienverstaendliche Erklaerung fuer den Kunden -- nur auf der Detailseite
// gezeigt, in der Liste waere es pro Zeile zu unruhig.
export const ANGEBOT_STATUS_ERKLAERUNG: Record<AngebotStatus, string> = {
  entwurf: "Dieses Angebot wird noch vorbereitet.",
  versendet: "Bitte prüfen Sie das Angebot und nehmen Sie es an oder lehnen Sie es ab.",
  angenommen: "Sie haben dieses Angebot angenommen.",
  abgelehnt: "Sie haben dieses Angebot abgelehnt.",
};
