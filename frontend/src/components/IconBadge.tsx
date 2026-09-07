import type { LucideIcon } from "lucide-react";

// "Industry"-Design (siehe docs/DESIGN.md): Icons stecken weiter in einem
// getonten Badge, um Bereichs-Familien optisch zu unterscheiden -- aber
// als Haarlinien-Quadrat statt gefuellter Pastell-Flaeche (Blaupausen-Optik
// kennt keine Fuellfarben ausser Akzent/Feld). Ton faerbt Rahmen + Icon,
// Hintergrund bleibt transparent.
export type IconTone =
  | "sky"
  | "violet"
  | "amber"
  | "rose"
  | "emerald"
  | "indigo"
  | "cyan"
  | "slate"
  | "teal";

const TONE_BADGE: Record<IconTone, string> = {
  sky: "border-sky-300 text-sky-600 dark:border-sky-800 dark:text-sky-400",
  violet: "border-violet-300 text-violet-600 dark:border-violet-800 dark:text-violet-400",
  amber: "border-amber-300 text-amber-600 dark:border-amber-800 dark:text-amber-400",
  rose: "border-rose-300 text-rose-600 dark:border-rose-800 dark:text-rose-400",
  emerald: "border-emerald-300 text-emerald-600 dark:border-emerald-800 dark:text-emerald-400",
  indigo: "border-indigo-300 text-indigo-600 dark:border-indigo-800 dark:text-indigo-400",
  cyan: "border-cyan-300 text-cyan-600 dark:border-cyan-800 dark:text-cyan-400",
  slate: "border-slate-300 text-slate-500 dark:border-stone-700 dark:text-stone-400",
  teal: "border-teal-300 text-teal-600 dark:border-teal-800 dark:text-teal-400",
};

export const TONE_ROW_ACTIVE: Record<IconTone, string> = {
  sky: "border-sky-400 bg-sky-50/60 text-sky-700 dark:border-sky-600 dark:bg-sky-500/10 dark:text-sky-300",
  violet:
    "border-violet-400 bg-violet-50/60 text-violet-700 dark:border-violet-600 dark:bg-violet-500/10 dark:text-violet-300",
  amber:
    "border-amber-400 bg-amber-50/60 text-amber-700 dark:border-amber-600 dark:bg-amber-500/10 dark:text-amber-300",
  rose: "border-rose-400 bg-rose-50/60 text-rose-700 dark:border-rose-600 dark:bg-rose-500/10 dark:text-rose-300",
  emerald:
    "border-emerald-400 bg-emerald-50/60 text-emerald-700 dark:border-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-300",
  indigo:
    "border-indigo-400 bg-indigo-50/60 text-indigo-700 dark:border-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300",
  cyan: "border-cyan-400 bg-cyan-50/60 text-cyan-700 dark:border-cyan-600 dark:bg-cyan-500/10 dark:text-cyan-300",
  slate: "border-slate-400 bg-slate-100 text-slate-700 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-200",
  teal: "border-teal-400 bg-teal-50/60 text-teal-700 dark:border-teal-600 dark:bg-teal-500/10 dark:text-teal-300",
};

const SIZE_BOX: Record<"sm" | "md", string> = {
  sm: "h-7 w-7 rounded-none",
  md: "h-9 w-9 rounded-none",
};

const SIZE_ICON: Record<"sm" | "md", number> = {
  sm: 15,
  md: 18,
};

const MUTED = "border-slate-300 text-slate-400 dark:border-stone-700 dark:text-stone-500";

export function IconBadge({
  icon: Icon,
  tone,
  size = "md",
  active = true,
}: {
  icon: LucideIcon;
  tone: IconTone;
  size?: "sm" | "md";
  /** Bei active=false erscheint das Badge neutral/grau -- fuer Zustaende, in
   * denen nur das gerade ausgewaehlte Element seine Farbe zeigen soll (z.B.
   * die enge Bottom-Nav), statt permanent eine ganze Farbreihe zu zeigen. */
  active?: boolean;
}) {
  return (
    <span
      aria-hidden
      className={`flex shrink-0 items-center justify-center border bg-transparent transition-colors duration-200 ${SIZE_BOX[size]} ${
        active ? TONE_BADGE[tone] : MUTED
      }`}
    >
      <Icon size={SIZE_ICON[size]} strokeWidth={1.5} />
    </span>
  );
}
