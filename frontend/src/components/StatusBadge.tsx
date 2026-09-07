import type { IconTone } from "./IconBadge";

// Ersetzt die in GeschaeftPage.tsx/RechnungDetailPage.tsx/
// RechnungseingangPage.tsx dreifach kopierte, immer neutral graue Pill-
// Klassenkette -- macht Status erstmals farblich unterscheidbar. Dieselbe
// Palette wie IconBadge (TONE_BADGE), hier aber lokal dupliziert, weil dort
// nicht exportiert. "Industry"-Design: Rahmen-Tag statt Pastell-Flaeche.
const TONE_PILL: Record<IconTone, string> = {
  sky: "border-sky-400 text-sky-700 dark:border-sky-600 dark:text-sky-300",
  violet: "border-violet-400 text-violet-700 dark:border-violet-600 dark:text-violet-300",
  amber: "border-amber-400 text-amber-700 dark:border-amber-600 dark:text-amber-300",
  rose: "border-rose-400 text-rose-700 dark:border-rose-600 dark:text-rose-300",
  emerald: "border-emerald-400 text-emerald-700 dark:border-emerald-600 dark:text-emerald-300",
  indigo: "border-indigo-400 text-indigo-700 dark:border-indigo-600 dark:text-indigo-300",
  cyan: "border-cyan-400 text-cyan-700 dark:border-cyan-600 dark:text-cyan-300",
  slate: "border-ind-line text-ind-ink-2",
  teal: "border-teal-400 text-teal-700 dark:border-teal-600 dark:text-teal-300",
};

export function StatusBadge({ label, tone }: { label: string; tone: IconTone }) {
  return (
    <span className={`border px-2 py-1 text-xs font-semibold ${TONE_PILL[tone]}`}>{label}</span>
  );
}
