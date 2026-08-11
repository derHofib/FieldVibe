import type { IconTone } from "../components/IconBadge";
import type { RechnungStatus } from "../types";

// Ersetzt die bisher dreifach duplizierten STATUS_LABEL-Maps
// (GeschaeftPage.tsx, RechnungDetailPage.tsx, PortalRechnungenPage.tsx).
export const RECHNUNG_STATUS_LABEL: Record<RechnungStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

export const RECHNUNG_STATUS_TONE: Record<RechnungStatus, IconTone> = {
  entwurf: "slate",
  versendet: "sky",
  bezahlt: "emerald",
  storniert: "rose",
};
