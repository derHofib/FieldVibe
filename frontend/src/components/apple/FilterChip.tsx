import { STATUS_KREIS_KLASSE, type StatusKey } from "./status";

/** Filter-Chip (Abschnitt 4.2). Erneuter Klick auf einen aktiven Chip hebt
 * den Filter wieder auf (Toggle-Verhalten liegt beim Aufrufer). */
export function FilterChip({
  label,
  anzahl,
  status,
  aktiv,
  onClick,
}: {
  label: string;
  anzahl?: number;
  status?: StatusKey;
  aktiv: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={aktiv}
      onClick={onClick}
      className={`inline-flex h-[26px] items-center gap-1.5 rounded-[13px] px-2.5 text-xs font-medium ${
        aktiv ? "bg-tint text-white" : "bg-fill text-label"
      }`}
    >
      {status && (
        <span
          className={`h-2.5 w-2.5 shrink-0 rounded-full ${aktiv ? "bg-white" : `bg-current ${STATUS_KREIS_KLASSE[status]}`}`}
          aria-hidden="true"
        />
      )}
      {label}
      {anzahl !== undefined && <span className={aktiv ? "opacity-80" : "opacity-70"}>{anzahl}</span>}
    </button>
  );
}
