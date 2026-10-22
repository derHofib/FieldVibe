import type { IconTone } from "../components/IconBadge";
import type { RechnungStatus } from "../types";
import { heuteIso } from "../utils/format";

// Backend kennt keinen eigenen "ueberfaellig"-Status (siehe RechnungStatus) --
// wird clientseitig aus Faelligkeitsdatum + Status abgeleitet, analog zu
// istUeberfaellig() fuer Vorgaenge in config/vorgangDarstellung.ts.
export function istRechnungUeberfaellig(rechnung: { faellig_am: string | null; status: RechnungStatus }): boolean {
  if (!rechnung.faellig_am) return false;
  if (rechnung.status === "bezahlt" || rechnung.status === "storniert") return false;
  return rechnung.faellig_am < heuteIso();
}

// Ersetzt die bisher dreifach duplizierten STATUS_LABEL-Maps
// (GeschaeftPage.tsx, RechnungDetailPage.tsx, PortalRechnungenPage.tsx).
export const RECHNUNG_STATUS_LABEL: Record<RechnungStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  teilweise_bezahlt: "Teilweise bezahlt",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

export const RECHNUNG_STATUS_TONE: Record<RechnungStatus, IconTone> = {
  entwurf: "slate",
  versendet: "sky",
  teilweise_bezahlt: "amber",
  bezahlt: "emerald",
  storniert: "rose",
};
