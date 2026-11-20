import type { DarstellungProps } from "./gemeinsam";
import { AKZENT } from "./gemeinsam";
import { Zahl } from "./Zahl";

const BREITE = 100;
const HOEHE = 36;

/** Zahl mit kleiner Verlaufsfläche. `daten` ist die Zeit-Aufteilung der Kennzahl; deren `gesamt` kommt in jeder
 * Antwort mit, ein zweiter Abruf für den Gesamtwert ist deshalb nicht nötig. */
export function ZahlVerlauf({ daten, vergleich, vorLabel, titel }: DarstellungProps) {
  const werte = daten.zeilen.map((z) => z.wert ?? 0);
  const hoechster = Math.max(...werte, 0);
  const punkte = werte.map((w, i) => {
    const x = werte.length > 1 ? (i / (werte.length - 1)) * BREITE : BREITE / 2;
    // 2px Rand oben/unten, damit die Linie nicht am Kartenrand abgeschnitten wird.
    const y = hoechster > 0 ? HOEHE - 2 - (w / hoechster) * (HOEHE - 4) : HOEHE - 2;
    return [x, y] as const;
  });
  const linie = punkte.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");

  return (
    <div className="flex flex-col gap-2">
      <Zahl daten={daten} vergleich={vergleich} vorLabel={vorLabel} />
      {punkte.length >= 2 && (
        <svg
          role="img"
          aria-label={`Verlauf: ${titel}`}
          viewBox={`0 0 ${BREITE} ${HOEHE}`}
          preserveAspectRatio="none"
          className="h-9 w-full"
        >
          <path d={`${linie} L${BREITE} ${HOEHE} L0 ${HOEHE} Z`} fill={AKZENT} fillOpacity={0.16} />
          <path
            d={linie}
            fill="none"
            stroke={AKZENT}
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      )}
    </div>
  );
}
