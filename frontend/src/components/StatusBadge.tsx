import { TONE_FILL, type IconTone } from "./IconBadge";

// Getoente Pille wie StatusPille: Text bleibt neutral (text-label, 4.5:1 in
// beiden Modi auf der Toenung), die Farbe traegt nur Flaeche und Punkt --
// Rohtoene als Text wuerden bei amber/emerald/cyan/teal auf Hell reissen.
const TONE_FLAECHE: Record<IconTone, string> = {
  sky: "bg-tone-sky/15",
  violet: "bg-tone-violet/15",
  amber: "bg-tone-amber/15",
  rose: "bg-tone-rose/15",
  emerald: "bg-tone-emerald/15",
  indigo: "bg-tone-indigo/15",
  cyan: "bg-tone-cyan/15",
  slate: "bg-fill",
  teal: "bg-tone-teal/15",
};

export function StatusBadge({ label, tone }: { label: string; tone: IconTone }) {
  return (
    <span
      className={`inline-flex items-center gap-[5px] rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-xs font-semibold text-label ${TONE_FLAECHE[tone]}`}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${TONE_FILL[tone]}`} aria-hidden="true" />
      {label}
    </span>
  );
}
