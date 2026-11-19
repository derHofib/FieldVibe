import { abweichung, formatWert } from "../format";
import type { DarstellungProps } from "./gemeinsam";

/** Gesamtwert groß, darunter die Abweichung zur Vorperiode. Gut/schlecht färbt nur bei Kennzahlen mit klarer
 * Richtung (siehe richtungFuer); der Pfeil steht zusätzlich als Text im Satz. */
export function Zahl({ daten, vergleich, vorLabel }: Pick<DarstellungProps, "daten" | "vergleich" | "vorLabel">) {
  const abw = vergleich
    ? abweichung(daten.kennzahl, daten.einheit, daten.gesamt, daten.vorperiode_gesamt, vorLabel)
    : null;
  const farbe = abw?.gut === true ? "text-st-erledigt" : abw?.gut === false ? "text-st-fehlt" : "text-label2";

  return (
    <div className="flex flex-col gap-1">
      <p className="ap-heading text-titel-desktop font-semibold tabular-nums text-label">
        {formatWert(daten.gesamt, daten.einheit)}
      </p>
      {abw && <p className={`text-sekundaer font-semibold ${farbe}`}>{abw.text}</p>}
      {daten.datumsbezug && <p className="text-sekundaer text-label2">{daten.datumsbezug}</p>}
    </div>
  );
}
