import { useId } from "react";

import { heuteIso } from "../../utils/format";
import { nachweisStatus, type NachweisArt } from "../../utils/steuer";
import { StatusPille } from "../apple/StatusPille";
import type { StatusKey } from "../apple/status";

// "fehlt" ist kein Fehler des Kunden, sondern ein leeres Feld -> neutral grau.
const STATUS_TOKEN: Record<NachweisArt, StatusKey> = {
  fehlt: "geplant",
  gueltig: "erledigt",
  laeuft_ab: "arbeit",
  abgelaufen: "fehlt",
};

export function Nachweis13bStatus({ bis }: { bis: string | null | undefined }) {
  const status = nachweisStatus(bis, heuteIso());
  return <StatusPille status={STATUS_TOKEN[status.art]} label={status.label} />;
}

/** Datumsfeld "§ 13b: Nachweis USt 1 TG gültig bis" mit Hilfetext und
 * Statuszeile -- im Kundenprofil und im Anlegen-Formular gleich. */
export function Nachweis13bFeld({
  wert,
  onChange,
}: {
  wert: string;
  onChange: (neu: string) => void;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs text-label2">
        § 13b: Nachweis USt 1 TG gültig bis
      </label>
      <input id={id} type="date" value={wert} onChange={(e) => onChange(e.target.value)} className="field-ap" />
      <p className="mt-1 text-xs text-label2">
        Bescheinigung des Leistungsempfängers nach § 13b Abs. 2 Nr. 4 UStG – nur für Reverse-Charge-Rechnungen nötig
      </p>
      <div className="mt-1.5">
        <Nachweis13bStatus bis={wert || null} />
      </div>
    </div>
  );
}
