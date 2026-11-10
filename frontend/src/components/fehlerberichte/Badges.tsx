import { StatusPille } from "../apple/StatusPille";
import type { FehlerberichtArt, FehlerberichtSchweregrad, FehlerberichtStatus } from "../../types";
import { FEHLER_STATUS_TOKEN, SCHWEREGRAD_KLASSE, SCHWEREGRAD_LABEL, statusLabel } from "./darstellung";

export function FehlerStatusPille({ status, art = "fehler" }: { status: FehlerberichtStatus; art?: FehlerberichtArt }) {
  return <StatusPille status={FEHLER_STATUS_TOKEN[status]} label={statusLabel(status, art)} />;
}

export function SchweregradBadge({ schweregrad }: { schweregrad: FehlerberichtSchweregrad }) {
  return (
    <span
      data-schweregrad={schweregrad}
      className={`inline-flex items-center rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-xs font-semibold ${SCHWEREGRAD_KLASSE[schweregrad]}`}
    >
      {SCHWEREGRAD_LABEL[schweregrad]}
    </span>
  );
}
