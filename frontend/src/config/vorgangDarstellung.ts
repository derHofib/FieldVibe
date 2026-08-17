import type { VorgangStatus } from "../types";

/** Beschriftungen und Farbklassen der Vorgangs-Status, gemeinsam genutzt von
 * Feld-App (pages/feld/FeedPage.tsx) und Desktop-Oberflaeche (office/). Zwei
 * Kopien wuerden bei jedem neuen Status auseinanderlaufen. */

export const STATUS_LABEL: Record<VorgangStatus, string> = {
  neu: "Neu",
  geplant: "Geplant",
  in_arbeit: "In Arbeit",
  wartet_kunde: "Wartet auf Kunde",
  abgeschlossen: "Abgeschlossen",
  abgerechnet: "Abgerechnet",
  storniert: "Storniert",
};

export const STATUS_BADGE: Record<VorgangStatus, string> = {
  neu: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300",
  geplant: "bg-purple-100 text-purple-800 dark:bg-purple-500/15 dark:text-purple-300",
  in_arbeit: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  wartet_kunde: "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300",
  abgeschlossen: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300",
  abgerechnet: "bg-slate-200 text-slate-700 dark:bg-stone-700 dark:text-stone-300",
  storniert: "bg-slate-100 text-slate-400 dark:bg-stone-800 dark:text-stone-500",
};

export const LEISTUNGSTYP_LABEL: Record<string, string> = {
  installation: "Installation",
  pruefung: "Prüfung",
  wartung: "Wartung",
  stoerung: "Störung",
  beratung: "Beratung",
  planung: "Planung",
};

/** Spalten des Kanban-Boards. "abgerechnet"/"storniert" fehlen bewusst -- sie
 * sind Endzustaende, die eine Arbeitsansicht nur zumuellen wuerden. */
export const KANBAN_SPALTEN: VorgangStatus[] = [
  "neu",
  "geplant",
  "in_arbeit",
  "wartet_kunde",
  "abgeschlossen",
];

export function istUeberfaellig(faelligkeitAm: string | null): boolean {
  if (!faelligkeitAm) return false;
  return faelligkeitAm < new Date().toISOString().slice(0, 10);
}

export function tageSeit(iso: string): number {
  const diff = Date.now() - new Date(iso).getTime();
  return Math.floor(diff / 86_400_000);
}
