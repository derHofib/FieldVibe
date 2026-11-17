import type { LucideIcon } from "lucide-react";

export interface KpiKachelProps {
  label: string;
  wert: string;
  zusatz?: string;
  icon?: LucideIcon;
  wertKlasse?: string;
}

/** Kompakte Variante der KennzahlKarte: Office-Seiten mit vielen Kennzahlen
 * (Arbeitszeit) brauchen ein Vielfaches an Kacheln, ohne den Kopf zu füllen. */
export function KpiKachel({ label, wert, zusatz, icon: Icon, wertKlasse = "text-label" }: KpiKachelProps) {
  return (
    <div className="card-ap px-3 py-2">
      <p className="flex items-center gap-1 truncate text-meta font-medium text-label2">
        {Icon && <Icon size={12} strokeWidth={2} aria-hidden="true" />}
        {label}
      </p>
      <p className={`ap-heading flex items-baseline gap-1.5 truncate text-titel-mobil font-semibold tabular-nums ${wertKlasse}`}>
        {wert}
        {zusatz && <span className="text-meta font-normal text-label2">{zusatz}</span>}
      </p>
    </div>
  );
}
