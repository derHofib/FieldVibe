import { StatusPille } from "../apple/StatusPille";
import type { FehlerberichtSchweregrad, FehlerberichtStatus } from "../../types";
import { FEHLER_STATUS_LABEL, FEHLER_STATUS_TOKEN, SCHWEREGRAD_KLASSE, SCHWEREGRAD_LABEL } from "./darstellung";

export function FehlerStatusPille({ status }: { status: FehlerberichtStatus }) {
  return <StatusPille status={FEHLER_STATUS_TOKEN[status]} label={FEHLER_STATUS_LABEL[status]} />;
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
