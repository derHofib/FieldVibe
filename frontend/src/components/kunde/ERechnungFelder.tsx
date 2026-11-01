import { useId } from "react";

import {
  E_RECHNUNG_FORMAT_OPTIONEN,
  type ERechnungFormat,
  LEITWEG_ID_FORMAT_HINWEIS,
  leitwegIdFehler,
} from "../../utils/eRechnungVersand";

/** Kundentypen, bei denen die E-Rechnung-Einstellungen sinnvoll sind (gewerblich); bei bereits
 * gesetzten Werten bleiben die Felder immer sichtbar, damit nichts unsichtbar weiterwirkt. */
export function zeigeERechnungFelder(typ: string | null | undefined, leitwegId: string, format: string): boolean {
  return typ === "gewerbe" || typ === "oeffentlich" || typ === "hausverwaltung" || !!leitwegId || !!format;
}

/** Leitweg-ID und Format der E-Rechnung -- im Kundenprofil und im Anlegen-Formular gleich. */
export function ERechnungFelder({
  leitwegId,
  format,
  onChange,
}: {
  leitwegId: string;
  format: ERechnungFormat | "";
  onChange: (neu: { leitwegId: string; format: ERechnungFormat | "" }) => void;
}) {
  const leitwegFeldId = useId();
  const formatFeldId = useId();
  const hilfeId = useId();
  const fehler = leitwegIdFehler(leitwegId);
  return (
    <div className="space-y-2">
      <div>
        <label htmlFor={leitwegFeldId} className="mb-1 block text-xs text-label2">
          Leitweg-ID
        </label>
        <input
          id={leitwegFeldId}
          value={leitwegId}
          onChange={(e) => onChange({ leitwegId: e.target.value, format })}
          placeholder="04011000-1234512345-06"
          aria-invalid={fehler !== null}
          aria-describedby={hilfeId}
          autoCapitalize="characters"
          className="field-ap"
        />
        {fehler ? (
          <p role="alert" className="mt-1 text-xs text-st-fehlt">
            {fehler}
          </p>
        ) : (
          <p id={hilfeId} className="mt-1 text-xs text-label2">
            Nur für Behörden und öffentliche Auftraggeber: Die Leitweg-ID steht im Auftrag oder auf der Webseite der
            Behörde. Mit Leitweg-ID wird die Rechnung automatisch als XRechnung erzeugt. {LEITWEG_ID_FORMAT_HINWEIS}
          </p>
        )}
      </div>
      <div>
        <label htmlFor={formatFeldId} className="mb-1 block text-xs text-label2">
          Format der E-Rechnung
        </label>
        <select
          id={formatFeldId}
          value={format}
          onChange={(e) => onChange({ leitwegId, format: e.target.value as ERechnungFormat | "" })}
          className="field-ap"
        >
          {E_RECHNUNG_FORMAT_OPTIONEN.map((o) => (
            <option key={o.wert} value={o.wert}>
              {o.label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-label2">
          XRechnung verlangt zusätzlich Telefon, E-Mail und IBAN in den Firmendaten sowie die Leitweg-ID.
        </p>
      </div>
    </div>
  );
}
