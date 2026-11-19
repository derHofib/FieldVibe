import { useState } from "react";

import { formatAchse, formatWert } from "../format";
import { AKZENT, achsenMaximum, beschriftungsAbstand, hatVorperiode, hoechsterWert, type DarstellungProps } from "./gemeinsam";

const PLOT_HOEHE = 200;

/** Verlaufslinie mit leichter Fläche; die Vorperiode läuft gestrichelt dahinter. Punkte und Wert erscheinen
 * nur unter der Maus -- Tastatur und Screenreader bekommen dieselben Zahlen über "Als Tabelle". */
export function Linie({ daten, groesse, vergleich, titel, vorLabel, zeitraumLabel }: DarstellungProps) {
  const [aktiv, setAktiv] = useState<number | null>(null);
  const mitVorperiode = hatVorperiode(daten, vergleich);
  const maximum = achsenMaximum(hoechsterWert(daten, mitVorperiode), daten.einheit);
  const anzahl = daten.zeilen.length;
  const abstand = beschriftungsAbstand(anzahl, groesse);

  const xProzent = (i: number) => (anzahl > 1 ? (i / (anzahl - 1)) * 100 : 50);
  const yProzent = (wert: number | null) => 100 - Math.max(0, Math.min(100, ((wert ?? 0) / maximum) * 100));
  const pfad = (werte: (number | null)[]) =>
    werte.map((w, i) => `${i === 0 ? "M" : "L"}${xProzent(i).toFixed(2)} ${yProzent(w).toFixed(2)}`).join(" ");

  const linie = pfad(daten.zeilen.map((z) => z.wert));
  const hoechste = daten.zeilen.reduce((a, z) => ((z.wert ?? -1) > (a?.wert ?? -1) ? z : a), daten.zeilen[0]);
  const gewaehlt = aktiv !== null ? daten.zeilen[aktiv] : null;

  return (
    <div
      role="img"
      aria-label={`Liniendiagramm: ${titel}, ${anzahl} Werte${
        hoechste?.wert != null ? `, höchster Wert ${formatWert(hoechste.wert, daten.einheit)} (${hoechste.label})` : ""
      }`}
      className="flex flex-col gap-2"
    >
      <div className="relative" style={{ height: PLOT_HOEHE }}>
        {[1, 2, 3].map((n) => (
          <div key={n} className="absolute inset-x-0 border-t-[0.5px] border-sep" style={{ bottom: `${(n / 3) * 100}%` }}>
            <span className="absolute -top-2 left-0 w-11 bg-card pr-1 text-meta tabular-nums text-label2">
              {formatAchse((maximum / 3) * n, daten.einheit)}
            </span>
          </div>
        ))}
        <div
          className="absolute inset-y-0 right-0 left-12 border-b-[0.5px] border-sepstrong"
          onMouseMove={(e) => {
            const rahmen = e.currentTarget.getBoundingClientRect();
            const anteil = rahmen.width > 0 ? (e.clientX - rahmen.left) / rahmen.width : 0;
            setAktiv(Math.max(0, Math.min(anzahl - 1, Math.round(anteil * (anzahl - 1)))));
          }}
          onMouseLeave={() => setAktiv(null)}
        >
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
            {mitVorperiode && (
              <path
                d={pfad(daten.zeilen.map((z) => z.vorperiode))}
                fill="none"
                stroke="var(--label3)"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                vectorEffect="non-scaling-stroke"
              />
            )}
            <path d={`${linie} L100 100 L0 100 Z`} fill="var(--tintbg)" />
            <path
              d={linie}
              fill="none"
              stroke={AKZENT}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
          {gewaehlt && aktiv !== null && (
            <>
              <span
                className="absolute h-2.5 w-2.5 -translate-x-1/2 translate-y-1/2 rounded-full border-2 border-card"
                style={{ left: `${xProzent(aktiv)}%`, bottom: `${100 - yProzent(gewaehlt.wert)}%`, background: AKZENT }}
              />
              <span
                className="pointer-events-none absolute top-0 right-0 rounded-md bg-fill px-2 py-0.5 text-meta font-semibold tabular-nums text-label"
                title={gewaehlt.label}
              >
                {gewaehlt.label}: {formatWert(gewaehlt.wert, daten.einheit)}
                {mitVorperiode && ` (${vorLabel}: ${formatWert(gewaehlt.vorperiode, daten.einheit)})`}
              </span>
            </>
          )}
        </div>
      </div>

      <div className="relative ml-12 h-4" aria-hidden="true">
        {daten.zeilen.map((zeile, i) =>
          i % abstand === 0 ? (
            <span
              key={zeile.schluessel}
              className="absolute text-meta whitespace-nowrap text-label2"
              style={{
                left: `${xProzent(i)}%`,
                transform: i === 0 ? "none" : i === anzahl - 1 ? "translateX(-100%)" : "translateX(-50%)",
              }}
            >
              {zeile.label}
            </span>
          ) : null,
        )}
      </div>

      {mitVorperiode && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 pl-12 text-meta text-label2" aria-hidden="true">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-3" style={{ background: AKZENT }} /> {zeitraumLabel ?? "Aktuell"}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0 w-3 border-t-2 border-dashed" style={{ borderColor: "var(--label3)" }} /> {vorLabel}
          </span>
        </div>
      )}
    </div>
  );
}
