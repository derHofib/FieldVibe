import { STATUS_PILLE_KLASSE, type StatusKey } from "./status";

/** Status-Pille (Abschnitt 4.2). Farbe transportiert den Status NIE allein
 * -- Punkt + Textlabel sind Pflicht (Abschnitt 6). */
export function StatusPille({ status, label }: { status: StatusKey; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-[5px] rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-xs font-semibold ${STATUS_PILLE_KLASSE[status]}`}
    >
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" aria-hidden="true" />
      {label}
    </span>
  );
}
