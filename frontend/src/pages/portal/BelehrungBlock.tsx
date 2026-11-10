import { Download } from "lucide-react";
import { useId } from "react";

import { Hinweiskasten } from "../../components/Hinweiskasten";
import { absaetze, ladeTextdatei } from "../../utils/portalAngebot";
import type { PortalVerbraucherschutz } from "../../types";

/** Widerrufsbelehrung samt Muster-Widerrufsformular. Der Text ist aufklappbar,
 * steht aber standardmaessig offen: er muss ohne Klick erreichbar sein. */
export function BelehrungBlock({
  daten,
  offen = true,
}: {
  daten: PortalVerbraucherschutz;
  offen?: boolean;
}) {
  const titelId = useId();
  if (!daten.belehrung) return null;
  const { belehrung } = daten;

  return (
    <section aria-labelledby={titelId} className="card-ap space-y-3 p-4">
      <h2 id={titelId} className="text-sm font-semibold text-label">
        Widerrufsbelehrung
      </h2>
      {belehrung.ist_platzhalter && (
        <Hinweiskasten ton="warnung" titel="Platzhalter – von Rechtsberatung prüfen">
          Der Betrieb hat noch keine eigene Widerrufsbelehrung hinterlegt. Dieser Text ist ein Muster.
        </Hinweiskasten>
      )}
      <details open={offen} className="group">
        <summary className="btn-touch cursor-pointer text-sm font-medium text-tint-text">
          Text der Widerrufsbelehrung (Stand {belehrung.version})
        </summary>
        <div className="mt-2 space-y-2 text-sm text-label">
          {absaetze(belehrung.text).map((absatz, i) => (
            <p key={i} className="whitespace-pre-line">
              {absatz}
            </p>
          ))}
        </div>
      </details>
      {daten.widerrufsformular_text && (
        <button
          type="button"
          onClick={() => ladeTextdatei("Muster-Widerrufsformular.txt", daten.widerrufsformular_text!)}
          className="btn-touch btn-ap flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium"
        >
          <Download size={14} strokeWidth={2} aria-hidden="true" />
          Muster-Widerrufsformular herunterladen
        </button>
      )}
    </section>
  );
}
