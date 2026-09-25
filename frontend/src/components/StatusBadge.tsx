import type { IconTone } from "./IconBadge";

// Ersetzt die in GeschaeftPage.tsx/RechnungDetailPage.tsx/
// RechnungseingangPage.tsx dreifach kopierte, immer neutral graue Pill-
// Klassenkette -- macht Status erstmals farblich unterscheidbar. Dieselbe
// Palette wie IconBadge (TONE_BADGE), hier aber lokal dupliziert, weil dort
// nicht exportiert. Rahmen-Tag statt Pastell-Flaeche, feste Bereichs-Toene
// (--tone-*) statt Tailwind-Palettenfarben.
const TONE_PILL: Record<IconTone, string> = {
  sky: "border-tone-sky text-tone-sky",
  violet: "border-tone-violet text-tone-violet",
  amber: "border-tone-amber text-tone-amber",
  rose: "border-tone-rose text-tone-rose",
  emerald: "border-tone-emerald text-tone-emerald",
  indigo: "border-tone-indigo text-tone-indigo",
  cyan: "border-tone-cyan text-tone-cyan",
  slate: "border-sep text-label",
  teal: "border-tone-teal text-tone-teal",
};

export function StatusBadge({ label, tone }: { label: string; tone: IconTone }) {
  return (
    <span className={`border px-2 py-1 text-xs font-semibold ${TONE_PILL[tone]}`}>{label}</span>
  );
}
