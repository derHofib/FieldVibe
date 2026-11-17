import { StatusPille } from "./apple/StatusPille";
import { vorgangStatusZuToken } from "./apple/status";
import { statusLabel } from "../config/vorgangDarstellung";
import type { VorgangStatus } from "../types";

/** Status-Pille für einen Vorgang-Status-String (z. B. aus Auswertungs-Maps
 * des Backends). Unbekannte Werte fallen auf eine neutrale Pille zurück,
 * statt eine Token-Farbe zu raten. */
export function VorgangStatusPille({ status, anzahl }: { status: string; anzahl?: number }) {
  const label = `${anzahl !== undefined ? `${anzahl}× ` : ""}${statusLabel(status)}`;
  if (status in VORGANG_STATUS_BEKANNT) {
    return <StatusPille status={vorgangStatusZuToken(status as VorgangStatus)} label={label} />;
  }
  return (
    <span className="inline-flex items-center rounded-[var(--radius-ap-pill)] bg-fill px-2 py-0.5 text-meta font-semibold text-label2">
      {label}
    </span>
  );
}

const VORGANG_STATUS_BEKANNT: Record<VorgangStatus, true> = {
  neu: true,
  geplant: true,
  in_arbeit: true,
  wartet_kunde: true,
  abgeschlossen: true,
  abgerechnet: true,
  storniert: true,
};
