import type { LucideIcon } from "lucide-react";

// Zentrale Farbpalette fuer "Variante 1" (siehe Design-Feedback): Icons
// stecken in einem dezenten Pastell-Badge statt als bunte Emoji direkt im
// Text zu stehen. Absichtlich nur gedaempfte 100/500-15%-Toene -- kraeftige
// Farben (400/600 als Flaeche) wuerden wieder "verspielt" statt "dezent"
// wirken.
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
  sky: "bg-sky-100 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300",
  violet: "bg-violet-100 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300",
  amber: "bg-amber-100 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300",
  rose: "bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300",
  emerald: "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300",
  indigo: "bg-indigo-100 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300",
  cyan: "bg-cyan-100 text-cyan-600 dark:bg-cyan-500/15 dark:text-cyan-300",
  slate: "bg-slate-100 text-slate-500 dark:bg-stone-800 dark:text-stone-400",
  teal: "bg-teal-100 text-teal-600 dark:bg-teal-500/15 dark:text-teal-300",
};

export const TONE_ROW_ACTIVE: Record<IconTone, string> = {
  sky: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300",
  violet: "bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-300",
  amber: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  rose: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300",
  emerald: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  indigo: "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300",
  cyan: "bg-cyan-50 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300",
  slate: "bg-slate-100 text-slate-700 dark:bg-stone-800 dark:text-stone-200",
  teal: "bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300",
};

const SIZE_BOX: Record<"sm" | "md", string> = {
  sm: "h-7 w-7 rounded-lg",
  md: "h-9 w-9 rounded-xl",
};

const SIZE_ICON: Record<"sm" | "md", number> = {
  sm: 15,
  md: 18,
};

const MUTED = "bg-slate-100 text-slate-400 dark:bg-stone-800/80 dark:text-stone-500";

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
      className={`flex shrink-0 items-center justify-center transition-colors duration-200 ${SIZE_BOX[size]} ${
        active ? TONE_BADGE[tone] : MUTED
      }`}
    >
      <Icon size={SIZE_ICON[size]} strokeWidth={2} />
    </span>
  );
}
