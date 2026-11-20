import { Phone, UserRound } from "lucide-react";

import { VOR_ORT_ROLLE_LABEL, type VorOrtHauptkontaktKurz } from "../../../types";
import { telHref } from "../../../utils/vorOrt";

/** Zeile auf der Feed-Karte: "Name (Rolle)" und rechts "Anrufen". Liegt neben (nicht in) dem Karten-Button, weil ein Link nicht in einem Button stehen darf. */
export function HauptkontaktZeile({ kontakt }: { kontakt: VorOrtHauptkontaktKurz | null | undefined }) {
  if (!kontakt) return null;
  const name = kontakt.name?.trim() || kontakt.telefon || VOR_ORT_ROLLE_LABEL[kontakt.rolle];
  const titel = kontakt.name?.trim() ? `${name} (${VOR_ORT_ROLLE_LABEL[kontakt.rolle]})` : name;
  return (
    <div className="flex items-center gap-2 border-t-[0.5px] border-sep px-3 py-2">
      <UserRound size={14} strokeWidth={1.5} className="shrink-0 text-label2" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate text-sekundaer text-label">{titel}</span>
      {kontakt.telefon && (
        <a
          href={telHref(kontakt.telefon)}
          aria-label={`${name} anrufen`}
          className="btn-touch inline-flex shrink-0 items-center gap-1.5 px-2 text-sekundaer font-medium text-tint-text"
        >
          <Phone size={14} strokeWidth={2} aria-hidden="true" />
          Anrufen
        </a>
      )}
    </div>
  );
}
