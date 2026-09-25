import { useQuery } from "@tanstack/react-query";

import { zeiterfassungApi } from "../api/endpoints";
import type { ZeiterfassungBuchungsstatus } from "../types";
import { BUCHUNGSSTATUS_LABEL, buchungsstatusZuToken } from "../utils/zeiterfassung";
import { StatusPille } from "./apple/StatusPille";

const STATUS_REIHENFOLGE: ZeiterfassungBuchungsstatus[] = ["vermerkt", "vorgemerkt", "gebucht", "abgerechnet"];

/** "Zeit"-Block fuers Auftrag-/Projekt-Panel (Stufe 4, docs/konzepte/
 * ZEITERFASSUNG.md Abschnitt 7.4): Summen ueber alle zugehoerigen Vorgaenge,
 * je Buchungsstatus. Reine Anzeige -- bearbeitet und gebucht wird weiterhin
 * am Vorgang bzw. auf der Sammelseite "Zeiten buchen". */
export function ZeitSummenBlock({ filter }: { filter: { auftrag_id: string } | { projekt_id: string } }) {
  const { data: summen } = useQuery({
    queryKey: ["zeiterfassung-summen", filter],
    queryFn: () => zeiterfassungApi.summen(filter),
  });

  if (!summen) return null;

  const zeilen = STATUS_REIHENFOLGE.map((status) => ({ status, summe: summen[status] })).filter(
    ({ summe }) => Number(summe.arbeitszeit_stunden) > 0 || Number(summe.fahrzeit_stunden) > 0,
  );

  return (
    <div>
      <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">Zeit</label>
      {zeilen.length === 0 ? (
        <p className="text-sm text-label2">Keine Zeit erfasst.</p>
      ) : (
        <div className="space-y-1.5">
          {zeilen.map(({ status, summe }) => (
            <div
              key={status}
              className="flex items-center justify-between gap-2 border border-sepstrong px-2.5 py-2 text-sm"
            >
              <StatusPille status={buchungsstatusZuToken(status)} label={BUCHUNGSSTATUS_LABEL[status]} />
              <span className="text-label2">
                {Number(summe.arbeitszeit_stunden) > 0 && `${summe.arbeitszeit_stunden} Std.`}
                {Number(summe.arbeitszeit_stunden) > 0 && Number(summe.fahrzeit_stunden) > 0 && " · "}
                {Number(summe.fahrzeit_stunden) > 0 &&
                  `${summe.fahrzeit_stunden} Std. Fahrzeit · ${summe.km} km`}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
