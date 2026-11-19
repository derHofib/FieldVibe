import { TabellenRahmen } from "../../OfficeUi";
import { abweichung, formatWert, KEIN_WERT } from "../format";
import { hatVorperiode, type DarstellungProps } from "./gemeinsam";

const KOPF = "px-3.5 py-2 text-meta font-bold tracking-wide text-label2 uppercase";

/** Genaue Werte je Zeile; mit Vorperiode kommen zwei Spalten dazu (Vorperiode, Abweichung). Dient zugleich als
 * Text-Alternative zu jedem Diagramm ("Als Tabelle"). */
export function Tabelle({ daten, vergleich, summierbar, vorLabel, titel }: DarstellungProps) {
  const mitVorperiode = hatVorperiode(daten, vergleich);
  const zeigeSumme = summierbar && daten.gesamt !== null;

  return (
    <TabellenRahmen>
      <table className="w-full border-collapse text-sekundaer" aria-label={titel}>
        <thead>
          <tr className="bg-fill">
            <th scope="col" className={`${KOPF} text-left`}>Gruppe</th>
            <th scope="col" className={`${KOPF} text-right`}>Wert</th>
            {mitVorperiode && <th scope="col" className={`${KOPF} text-right`}>{vorLabel}</th>}
            {mitVorperiode && <th scope="col" className={`${KOPF} text-right`}>Abweichung</th>}
          </tr>
        </thead>
        <tbody>
          {daten.zeilen.map((zeile) => {
            const abw = mitVorperiode
              ? abweichung(daten.kennzahl, daten.einheit, zeile.wert, zeile.vorperiode, vorLabel)
              : null;
            return (
              <tr key={zeile.schluessel} className="border-b border-sep last:border-b-0">
                <td className="px-3.5 py-2 text-label">{zeile.label}</td>
                <td className="px-3.5 py-2 text-right font-semibold tabular-nums text-label">
                  {formatWert(zeile.wert, daten.einheit)}
                </td>
                {mitVorperiode && (
                  <td className="px-3.5 py-2 text-right tabular-nums text-label2">
                    {formatWert(zeile.vorperiode, daten.einheit)}
                  </td>
                )}
                {mitVorperiode && (
                  <td
                    className={`px-3.5 py-2 text-right tabular-nums ${
                      abw?.gut === true ? "text-st-erledigt" : abw?.gut === false ? "text-st-fehlt" : "text-label2"
                    }`}
                  >
                    {abw ? abw.kurz : KEIN_WERT}
                  </td>
                )}
              </tr>
            );
          })}
          {zeigeSumme && (
            <tr className="border-t border-sepstrong">
              <td className="px-3.5 py-2 font-semibold text-label">Gesamt</td>
              <td className="px-3.5 py-2 text-right font-semibold tabular-nums text-label">
                {formatWert(daten.gesamt, daten.einheit)}
              </td>
              {mitVorperiode && (
                <td className="px-3.5 py-2 text-right tabular-nums text-label2">
                  {formatWert(daten.vorperiode_gesamt, daten.einheit)}
                </td>
              )}
              {mitVorperiode && <td />}
            </tr>
          )}
        </tbody>
      </table>
    </TabellenRahmen>
  );
}
