import type { IconTone } from "./IconBadge";

// Ersetzt die in GeschaeftPage.tsx/RechnungDetailPage.tsx/
// RechnungseingangPage.tsx dreifach kopierte, immer neutral graue Pill-
// Klassenkette -- macht Status erstmals farblich unterscheidbar. Dieselbe
// Palette wie IconBadge (TONE_BADGE), hier aber lokal dupliziert, weil dort
// nicht exportiert.
const TONE_PILL: Record<IconTone, string> = {
  sky: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  violet: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  amber: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  rose: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
  emerald: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  indigo: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
  cyan: "bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-300",
  slate: "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300",
  teal: "bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300",
};

export function StatusBadge({ label, tone }: { label: string; tone: IconTone }) {
  return (
    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${TONE_PILL[tone]}`}>
      {label}
    </span>
  );
}
