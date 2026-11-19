import { formatAchse, formatWert } from "../format";
import {
  VORPERIODE_FARBE,
  achsenMaximum,
  beschriftungsAbstand,
  hatVorperiode,
  hoechsterWert,
  zeilenFarbe,
  type DarstellungProps,
} from "./gemeinsam";

const PLOT_HOEHE = 200;

/** Senkrechte Säulen je Zeile (Zeit oder Kategorie); die Vorperiode steht als graue Säule links neben der aktuellen.
 * Eigenes HTML statt Diagramm-Bibliothek: Schrift bleibt unverzerrt, Farben kommen direkt aus den Token. */
export function Saeulen({ daten, groesse, vergleich, statusFarben, titel, vorLabel, zeitraumLabel }: DarstellungProps) {
  const mitVorperiode = hatVorperiode(daten, vergleich);
  const maximum = achsenMaximum(hoechsterWert(daten, mitVorperiode), daten.einheit);
  const abstand = beschriftungsAbstand(daten.zeilen.length, groesse);
  const prozent = (wert: number | null) => `${Math.max(0, Math.min(100, ((wert ?? 0) / maximum) * 100))}%`;
  const hoechste = daten.zeilen.reduce((a, z) => ((z.wert ?? -1) > (a?.wert ?? -1) ? z : a), daten.zeilen[0]);

  return (
    <div
      role="img"
      aria-label={`Säulendiagramm: ${titel}, ${daten.zeilen.length} Werte${
        hoechste?.wert != null ? `, höchster Wert ${formatWert(hoechste.wert, daten.einheit)} (${hoechste.label})` : ""
      }`}
      className="flex flex-col gap-2"
    >
      <div className="relative" style={{ height: PLOT_HOEHE }}>
        {[1, 2, 3].map((n) => (
          <div
            key={n}
            className="absolute inset-x-0 border-t-[0.5px] border-sep"
            style={{ bottom: `${(n / 3) * 100}%` }}
          >
            <span className="absolute -top-2 left-0 w-11 bg-card pr-1 text-meta tabular-nums text-label2">
              {formatAchse((maximum / 3) * n, daten.einheit)}
            </span>
          </div>
        ))}
        <div className="absolute inset-y-0 right-0 left-12 flex items-end gap-1 border-b-[0.5px] border-sepstrong">
          {daten.zeilen.map((zeile) => (
            <div
              key={zeile.schluessel}
              className="flex h-full min-w-0 flex-1 items-end justify-center gap-0.5"
              title={`${zeile.label}: ${formatWert(zeile.wert, daten.einheit)}${
                mitVorperiode ? ` (${vorLabel}: ${formatWert(zeile.vorperiode, daten.einheit)})` : ""
              }`}
            >
              {mitVorperiode && (
                <div
                  className="w-full max-w-5 rounded-t-[3px]"
                  style={{ height: prozent(zeile.vorperiode), background: VORPERIODE_FARBE }}
                />
              )}
              <div
                className="w-full max-w-5 rounded-t-[3px]"
                style={{ height: prozent(zeile.wert), background: zeilenFarbe(zeile, statusFarben) }}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-1 pl-12" aria-hidden="true">
        {daten.zeilen.map((zeile, i) => (
          <span key={zeile.schluessel} className="min-w-0 flex-1 truncate text-center text-meta text-label2">
            {i % abstand === 0 ? zeile.label : ""}
          </span>
        ))}
      </div>

      {mitVorperiode && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 pl-12 text-meta text-label2" aria-hidden="true">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-[2px]" style={{ background: "var(--tint)" }} /> {zeitraumLabel ?? "Aktuell"}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-[2px]" style={{ background: VORPERIODE_FARBE }} /> {vorLabel}
          </span>
        </div>
      )}
    </div>
  );
}
