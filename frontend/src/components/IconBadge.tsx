import type { LucideIcon } from "lucide-react";

// Icons stecken in einer gefuellten Kachel (Form wie SymbolKachel), um fachlich unabhaengige Bereiche
// (Kunden/Partner/Material/...) optisch zu unterscheiden -- reine
// Kategorie-Farbe, kein Status/keine Herkunft (Abschnitt 3.3-Ausnahme wie
// die Symbol-Kacheln: feste Bereichs-Toene, in beiden Modi identisch,
// siehe --tone-* in index.css).
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

// Weisses Icon braucht >=3:1 auf der Flaeche -- deshalb --tone-*-fill statt
// der Rohtoene (amber/emerald/cyan/teal waeren zu hell).
export const TONE_FILL: Record<IconTone, string> = {
  sky: "bg-tone-sky-fill",
  violet: "bg-tone-violet-fill",
  amber: "bg-tone-amber-fill",
  rose: "bg-tone-rose-fill",
  emerald: "bg-tone-emerald-fill",
  indigo: "bg-tone-indigo-fill",
  cyan: "bg-tone-cyan-fill",
  slate: "bg-tone-slate-fill",
  teal: "bg-tone-teal-fill",
};

export const TONE_ROW_ACTIVE: Record<IconTone, string> = {
  sky: "border-tone-sky bg-tone-sky/10 text-tone-sky",
  violet: "border-tone-violet bg-tone-violet/10 text-tone-violet",
  amber: "border-tone-amber bg-tone-amber/10 text-tone-amber",
  rose: "border-tone-rose bg-tone-rose/10 text-tone-rose",
  emerald: "border-tone-emerald bg-tone-emerald/10 text-tone-emerald",
  indigo: "border-tone-indigo bg-tone-indigo/10 text-tone-indigo",
  cyan: "border-tone-cyan bg-tone-cyan/10 text-tone-cyan",
  slate: "border-sepstrong bg-fill text-label",
  teal: "border-tone-teal bg-tone-teal/10 text-tone-teal",
};

const SIZE_BOX: Record<"sm" | "md", string> = {
  sm: "h-7 w-7 rounded-[7px]",
  md: "h-9 w-9 rounded-[7px]",
};

const SIZE_ICON: Record<"sm" | "md", number> = {
  sm: 15,
  md: 18,
};

const MUTED = "bg-fill text-label2";

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
        active ? `${TONE_FILL[tone]} text-white` : MUTED
      }`}
    >
      <Icon size={SIZE_ICON[size]} strokeWidth={2} />
    </span>
  );
}
