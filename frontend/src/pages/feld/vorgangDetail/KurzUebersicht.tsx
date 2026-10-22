import type { Vorgang } from "../../../types";
import { ABRECHNUNGSART_LABEL, LEISTUNGSTYP_LABEL, STATUS_LABEL } from "./konstanten";

interface KurzUebersichtProps {
  layout: "kompakt" | "dicht";
  vorgang: Vorgang;
}

/** Tab-übergreifend angeheftete Kurzübersicht im dichten Layout. */
export function KurzUebersicht({ layout, vorgang }: KurzUebersichtProps) {
  return (
    <>
      {/* Kurzuebersicht: bisher Teil des Uebersicht-Tabs (nur dort sichtbar),
       * jetzt tab-uebergreifend oben angeheftet -- Status/Prioritaet/
       * Zustaendigkeit bleiben so auch auf Zeit/Termine/Maengel/Positionen/
       * Verlauf im Blick, ohne dafuer zurueck zu tabben. */}
      {layout === "dicht" && (
        <div className="card-ap mb-3 space-y-2.5 p-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm lg:grid-cols-4">
            {[
              ["Status", STATUS_LABEL[vorgang.status]],
              ["Priorität", String(vorgang.prioritaet)],
              ["Zugewiesen an", vorgang.zugewiesener_name ?? "Nicht zugewiesen"],
              [
                "Fälligkeit",
                vorgang.faelligkeit_am ? new Date(vorgang.faelligkeit_am).toLocaleDateString("de-DE") : "—",
              ],
              ["Leistungstyp", LEISTUNGSTYP_LABEL[vorgang.leistungstyp]],
              ["Abrechnungsart", ABRECHNUNGSART_LABEL[vorgang.abrechnungsart]],
              ["Erstellt am", new Date(vorgang.created_at).toLocaleDateString("de-DE")],
            ].map(([label, wert]) => (
              <div key={label} className="flex items-baseline justify-between gap-2 lg:flex-col lg:items-start lg:gap-0.5">
                <dt className="text-xs text-label2">{label}</dt>
                <dd className="text-right font-medium text-label lg:text-left">{wert}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </>
  );
}
